"""Stage 8 evidence: compare existing XC90 source-linked articles with Oracle OEM.

Read-only. Works in live catalogue-api process; no new deployment required when
executed via python -c. No article_li / article_links, warehouse, imports or VIN APIs.
An OEM reference is cross-reference evidence, not physical fitment.
"""
from datetime import datetime, timezone
import json
import os

MAX_ARTICLES = 24
MAX_OEM = 20


def audit(snapshot, enrich, request):
    data, digest = snapshot(107555)
    if data.get("manufacturer_id") != 120 or data.get("car_id") != 107555:
        raise ValueError("Wrong Volvo source identity")
    graph = data.get("articles")
    if not isinstance(graph, dict) or not isinstance(data.get("categories"), list):
        raise ValueError("Invalid source graph")
    linked = set()
    diverse = []
    for cat in data["categories"]:
        if not isinstance(cat, dict):
            raise ValueError("Invalid source category")
        keys = cat.get("articles", [])
        for key in keys:
            if key not in graph:
                raise ValueError("Missing source article")
            linked.add(key)
        if keys:
            diverse.append((cat["product_id"], keys[0]))
    if not linked:
        raise ValueError("No source-linked articles; do not infer coverage")

    # Select true modification-linked offers, not unconnected supplier articles.
    # Prioritize known snapshot OE evidence, then spread remaining offers across
    # different PRD types to avoid one-product sampling bias.
    priority = sorted(key for key in linked if graph[key].get("oem"))[:12]
    chosen = list(priority)
    for _, key in sorted(diverse):
        if len(chosen) == MAX_ARTICLES:
            break
        if key not in chosen:
            chosen.append(key)
    if len(chosen) < MAX_ARTICLES:
        chosen.extend(key for key in sorted(linked) if key not in chosen) 
        chosen = chosen[:MAX_ARTICLES]

    local = enrich(data, chosen)
    results = []
    for key in chosen:
        part = graph[key]
        if type(part.get("supplier_id")) is not int or not isinstance(part.get("article_number"), str):
            raise ValueError("Invalid source article key")
        sid, number = part["supplier_id"], part["article_number"]
        if not 1 <= sid <= 65535 or not 1 <= len(number) <= 64:
            raise ValueError("Unsafe source article")
        imported = local.get(key, {})
        refs = imported.get("oem") or []
        local_numbers = sorted({
            str(oe.get("OENbr") or oe.get("oenbr")).strip()
            for oe in refs if isinstance(oe, dict)
            and int(oe.get("manufacturerId") or oe.get("manufacturerid") or 0) == 120
            and (oe.get("OENbr") or oe.get("oenbr"))
        })
        row = {"supplier_id": sid, "article_number": number,
               "source_oem_count": len(local_numbers),
               "source_oem_sample": local_numbers[:5]}
        try:
            upstream = request("/api/v1/oracle/oem/by-article",
                               {"supplier_id": sid, "article_number": number,
                                "manufacturer_id": 120, "limit": MAX_OEM})
            if not isinstance(upstream, dict) or upstream.get("fitment_verified") is not False \
                    or type(upstream.get("truncated")) is not bool \
                    or not isinstance(upstream.get("items"), list) \
                    or len(upstream["items"]) > MAX_OEM:
                raise ValueError("Invalid Oracle OE contract")
            values = upstream["items"]
            if any(not isinstance(v, dict) or not isinstance(v.get("oem_number"), str)
                   for v in values):
                raise ValueError("Invalid Oracle OE rows")
            remote = sorted({v["oem_number"] for v in values})
            row.update(oracle_status="ok", oracle_oem_count=len(remote),
                       oracle_oem_sample=remote[:5],
                       oracle_truncated=upstream["truncated"],
                       common_count=len(set(remote) & set(local_numbers)))
        except Exception as exc:
            row.update(oracle_status="failed", error_class=type(exc).__name__)
        results.append(row)

    supplemental = []
    for label, kind, car_id in [
        ("XC90_T6", "passenger", 107555),
        ("XC60_T5_reference_NOT_B5", "passenger", 126480),
        ("DAF_XF105_candidate", "commercial", 8387),
    ]:
        try:
            res = request("/api/v1/oracle/vehicles/attributes",
                          {"kind": kind, "car_id": car_id, "limit": 50})
            if res.get("vehicle_identity_only") is not True or res.get("fitment_verified") is not False \
                    or not isinstance(res.get("items"), list):
                raise ValueError("Untrusted identity result")
            attrs = res["items"]
            supplemental.append({"label": label, "car_id": car_id, "kind": kind,
                                 "rows": len(attrs), "sample": attrs[:20], "status": "ok"})
        except Exception as exc:
            supplemental.append({"label": label, "car_id": car_id,
                                 "status": "failed", "error_class": type(exc).__name__})

    return {
        "stage": "8_source_graph", "utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "fitment_verified": False,
        "excluded_tables": ["article_li", "article_links"],
        "source_modification_id": 107555, "source_snapshot_sha": digest,
        "source_scope": data.get("source_scope"), "source_coverage": data.get("coverage"),
        "source_categories": len(data["categories"]),
        "source_linked_article_keys": len(linked),
        "source_linked_articles_with_snapshot_oem": sum(
            bool(graph[key].get("oem")) for key in linked),
        "sampled": len(results),
        "local_oe_positive": sum(bool(x.get("source_oem_count")) for x in results),
        "oracle_oe_positive": sum(bool(x.get("oracle_oem_count")) for x in results),
        "oracle_query_failed": sum(x.get("oracle_status") != "ok" for x in results),
        "items": results,
        "modification_attributes": supplemental,
        "note": "Source association and OEM cross-reference only; not confirmed VIN/physical fitment.",
    }


def main():
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") != "catalogue-staging":
        raise SystemExit("STOP: catalogue-staging only")
    from app import volvo_snapshot, enrich_linked_articles
    from oracle_gateway import _request
    print("STAGE8_SOURCE_GRAPH_START", flush=True)
    print(json.dumps(audit(volvo_snapshot, enrich_linked_articles, _request),
                     ensure_ascii=True, indent=2), flush=True)
    print("STAGE8_SOURCE_GRAPH_END", flush=True)


if __name__ == "__main__":
    main()
