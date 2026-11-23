"""CarPot Stage 8 live Oracle OEM audit (read-only, source associations only).

Run inside existing catalogue-api STAGING container: python stage8_live_oem_audit.py
Uses only the existing authenticated, bounded oracle_gateway._request route.
Never queries article_li/article_links, changes stock, pays VIN providers, or
treats source OEM cross-references as verified physical compatibility.
"""
from datetime import datetime, timezone
import json
import os

MAX_PAGES = 6
PAGE_SIZE = 50
XC90_MODIFICATION_ID = 107555
KNOWN_VOLVO_MODELS = {"xc90": 13084, "xc60": 37773}


def _checked(data, vehicle=False):
    if not isinstance(data, dict) or type(data.get("truncated")) is not bool:
        raise ValueError("Untrusted Oracle response")
    if data.get("fitment_verified") is not False:
        raise ValueError("Fitment must not be inferred")
    if vehicle and data.get("vehicle_identity_only") is not True:
        raise ValueError("Missing source-identity marker")
    rows = data.get("items")
    if not isinstance(rows, list) or len(rows) > PAGE_SIZE or any(not isinstance(r, dict) for r in rows):
        raise ValueError("Unbounded Oracle response")
    return rows


def audit(request):
    checks = []
    def read(name, path, params, vehicle=False):
        try:
            data = request(path, params)
            rows = _checked(data, vehicle=vehicle)
            checks.append({"name": name, "status": "ok", "rows": len(rows)})
            return data, rows
        except Exception as exc:
            # Error types only; no secrets, URLs or SQL diagnostics in results.
            checks.append({"name": name, "status": "failed", "error_class": type(exc).__name__})
            return None, []

    makers = {}
    models = {}
    for make, kind in (("Volvo", "passenger"), ("DAF", "commercial")):
        _, rows = read(make + "_makers", "/api/v1/oracle/vehicles/manufacturers",
                       {"name": make, "kind": kind, "limit": 20}, vehicle=True)
        exact = sorted({r["id"] for r in rows
                        if type(r.get("id")) is int and r["id"] > 0
                        and str(r.get("name", "")).casefold() == make.casefold()})
        makers[make] = {"kind": kind, "manufacturer_ids": exact}
        found = {}
        for manufacturer_id in exact[:2]:
            after = 0
            for page in range(MAX_PAGES):
                data, batch = read(make + "_models_" + str(page + 1),
                                   "/api/v1/oracle/vehicles/models",
                                   {"manufacturer_id": manufacturer_id, "kind": kind,
                                    "after": after, "limit": PAGE_SIZE}, vehicle=True)
                if data is None:
                    break
                ids = [r.get("id") for r in batch]
                if any(type(i) is not int or i <= after for i in ids) or ids != sorted(set(ids)):
                    checks.append({"name": make + "_models_cursor",
                                   "status": "failed", "error_class": "InvalidIds"})
                    break
                for row in batch:
                    name = str(row.get("name", "")).casefold()
                    if any(term in name for term in (("xc90", "xc60") if make == "Volvo" else ("xf",))):
                        found[row["id"]] = {"id": row["id"], "name": row.get("name"),
                                             "years": row.get("construction_interval")}
                if not data["truncated"]:
                    break
                if not batch or type(data.get("next_after")) is not int or data["next_after"] != batch[-1]["id"]:
                    checks.append({"name": make + "_models_cursor",
                                   "status": "failed", "error_class": "InvalidNextAfter"})
                    break
                after = data["next_after"]
        models[make] = list(sorted(found.values(), key=lambda x: x["id"]))[:6]

    source_models = [("XC90", "passenger", KNOWN_VOLVO_MODELS["xc90"]),
                     ("XC60", "passenger", KNOWN_VOLVO_MODELS["xc60"])]
    source_models.extend(("DAF_" + str(m["id"]), "commercial", m["id"])
                         for m in models["DAF"][:2])
    modifications = {}
    for label, kind, model_id in source_models:
        data, rows = read(label + "_modifications", "/api/v1/oracle/vehicles/modifications",
                          {"model_id": model_id, "kind": kind,
                           "after": 0, "limit": PAGE_SIZE}, vehicle=True)
        valid = [r for r in rows if type(r.get("id")) is int and r["id"] > 0
                 and type(r.get("model_id")) is int and r["model_id"] == model_id]
        if len(valid) != len(rows):
            checks.append({"name": label + "_identity", "status": "failed",
                           "error_class": "WrongModelId"})
        modifications[label] = {"model_id": model_id, "items": valid,
                                "truncated": data["truncated"] if data else None}

    _, attrs = read("XC90_attributes", "/api/v1/oracle/vehicles/attributes",
                    {"car_id": XC90_MODIFICATION_ID, "kind": "passenger",
                     "limit": PAGE_SIZE}, vehicle=True)
    _, prd = read("XC90_PRD", "/api/v1/oracle/vehicles/" +
                  str(XC90_MODIFICATION_ID) + "/prd", {"limit": 20})
    reference_samples = []
    for sid, article in ((112, "F11-84-017-01-FA"), (30, "0 272 220 823")):
        data, refs = read("XC90_OEM_" + str(sid), "/api/v1/oracle/oem/by-article",
                          {"supplier_id": sid, "article_number": article,
                           "manufacturer_id": 120, "limit": 20})
        reference_samples.append({"supplier_id": sid, "article_number": article,
                                  "oem_numbers": [r["oem_number"] for r in refs
                                                  if isinstance(r.get("oem_number"), str)],
                                  "truncated": data["truncated"] if data else None})
    return {
        "stage": 8, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "fitment_verified": False,
        "excluded_tables": ["article_li", "article_links"],
        "manufacturers": makers, "candidate_models": models,
        "modifications": modifications,
        "xc90_attributes_sample": attrs, "xc90_prd_sample": prd,
        "oem_reference_samples": reference_samples, "checks": checks,
        "limitations": [
            "Read-only bounded sampling, not full OEM coverage.",
            "Catalogue source associations are not verified VIN fitment.",
            "DAF commercial PRD requires schema/grant verification.",
            "XC60 B5 must not be silently matched to T5.",
        ],
    }


def main():
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") != "catalogue-staging":
        raise SystemExit("STOP: staging only")
    import oracle_gateway
    result = audit(oracle_gateway._request)
    print("STAGE8_READONLY_AUDIT_START")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    print("STAGE8_READONLY_AUDIT_END")
    if any(c["status"] == "failed" for c in result["checks"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
