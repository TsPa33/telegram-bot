"""VIN intake over the read-only Oracle directory and pinned Catalogue plans."""
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import secrets
import time
import zlib

from fastapi import HTTPException

from app.services import unified_catalogue as catalogue
from app.services import vin_source_directory as directory
from app.services import vin_resolution_policy as policy
from app.services.catalogue_format import digest

_CONTEXT_TTL = 30 * 60
_RUNTIME_KEY = secrets.token_bytes(32)
_MAX_MAKERS = 4
_MAX_MODELS = 4
_MAX_VARIANTS = 16


def _signature(purpose, payload):
    configured = os.getenv("WAREHOUSE_CATALOGUE_KEY", "").encode()
    key = hmac.digest(configured or _RUNTIME_KEY, b"carpot/warehouse/vin-resolution/v1", "sha256")
    return hmac.new(key, purpose.encode() + b"." + payload.encode(), hashlib.sha256).hexdigest()


def _binding(who):
    return [who.workspace_account_id, who.actor_id, hashlib.sha256(who.session.token_hash.encode()).hexdigest()]


def _sign(purpose, payload, who):
    payload = base64.urlsafe_b64encode(zlib.compress(json.dumps(
        [int(time.time()) + _CONTEXT_TTL, _binding(who), payload], ensure_ascii=False,
        separators=(",", ":"),
    ).encode())).decode()
    return f"{payload}.{_signature(purpose, payload)}"


def _read(purpose, token, who, limit):
    if not token or len(token) > limit:
        raise HTTPException(409, "Оновіть розпізнавання VIN і повторіть вибір")
    try:
        payload, mac = token.split(".")
        if not payload.isascii() or not mac.isascii() or not hmac.compare_digest(_signature(purpose, payload), mac):
            raise ValueError()
        expires, binding, contents = json.loads(zlib.decompress(base64.urlsafe_b64decode(payload)))
        if expires <= time.time() or binding != _binding(who):
            raise ValueError()
        return contents
    except (ValueError, TypeError, binascii.Error, zlib.error):
        raise HTTPException(409, "Контекст VIN застарів. Повторіть розпізнавання") from None


def issue_context(decoded, who):
    vehicle = decoded.get("vehicle", {})
    conflicts = decoded.get("conflicts") or {}
    issues = decoded.get("consistency_issues") or {}
    sources = decoded.get("field_sources", {})
    observations = {}
    for field in policy.FIELDS:
        reported = str(vehicle.get(field) or "")[:160]
        alternatives = conflicts.get(field) or {}
        disputed = field in issues or field in conflicts
        if reported or disputed:
            observations[field] = {
                "reported": reported,
                "source": str(sources.get(field) or decoded.get("source") or "")[:100],
                "confidence": "conflict" if disputed else "reported",
                **({"alternative": str(alternatives.get("secondary") or "")[:160]} if alternatives else {}),
            }
    return _sign("decode", {"vin": decoded["vin"], "observations": observations,
                            "details": {key: decoded[key] for key in (
                                "vehicle", "field_sources", "diagnostics", "additional", "conflicts",
                                "consistency_issues", "source", "observed_at") if key in decoded}}, who)


def trusted_context(token, who, vin=None):
    context = _read("decode", token, who, 12000)
    if vin is not None and context["vin"] != vin:
        raise HTTPException(409, "Дані декодування належать іншому VIN")
    return context


def _value(field, reported):
    normalized = policy.normalized(field, reported)
    return str(reported).strip() if field == "model" and normalized else normalized


def effective_evidence(context, clarifications):
    evidence = {}
    original = context["observations"]
    for field, observation in original.items():
        value = None if observation["confidence"] == "conflict" else _value(field, observation["reported"])
        evidence[field] = {**observation, "value": value}
    for field, answer in clarifications.answers.items():
        if field not in policy.FIELDS:
            raise HTTPException(422, "Непідтримуване уточнення VIN")
        value = _value(field, answer)
        if answer and value is None:
            raise HTTPException(422, "Не вдалося розпізнати значення уточнення")
        evidence[field] = {"value": value, "reported": answer or "", "source": "operator",
                           "confidence": "clarified" if value is not None else "unknown"}
    correction = clarifications.model_correction
    if correction:
        evidence["model"] = {"value": correction, "reported": correction,
                             "source": "operator", "confidence": "corrected"}
    hp = evidence.pop("engine_power_hp", None)
    kw = evidence.get("engine_power_kw")
    if not kw and hp and hp["confidence"] == "conflict":
        evidence["engine_power_kw"] = hp
    if hp and hp["value"] is not None:
        if not kw:
            evidence["engine_power_kw"] = hp
        elif kw["value"] is not None and not policy.equivalent("engine_power_kw", kw["value"], hp["value"]):
            evidence["engine_power_kw"] = {**kw, "value": None, "confidence": "conflict"}
    return evidence


def _model_facts(maker, model):
    return {"manufacturer": maker["manufacturer"], "model": model["name"],
            "model_period": policy.interval(model.get("construction_interval")),
            "variant_period": (None, None), "specs": {
                "manufacturer": {policy.normalized("manufacturer", maker["manufacturer"]): maker["manufacturer"]},
                "vehicle_type": {maker["kind"]: maker["kind"]},
            }}


def _locator(maker, model, variant):
    return {"kind": maker["kind"], "manufacturer_id": maker["manufacturer_id"],
            "model_id": model["id"], "source_modification_id": variant["id"]}


def _attributes(adapter, locator):
    result = directory.fetch(adapter, "attributes", {
        "car_id": locator["source_modification_id"], "kind": locator["kind"], "limit": 50,
    }, locator["kind"])
    if (result.get("source_modification_id") != locator["source_modification_id"]
            or len(result["items"]) > 50 or any(not isinstance(item, dict) for item in result["items"])):
        raise HTTPException(503, "Некоректні характеристики модифікації")
    return policy.source_specs(result["items"]), result.get("truncated") is False


def _candidate(adapter, maker, model, variant):
    locator = _locator(maker, model, variant)
    facts = _model_facts(maker, model)
    facts["variant_period"] = policy.interval(variant.get("construction_interval"))
    try:
        specs, complete = _attributes(adapter, locator)
    except HTTPException as error:
        if error.status_code != 503:
            raise
        specs, complete = {}, False
    facts["specs"].update(specs)
    return {**facts, **locator, "modification": variant["name"],
            "construction_interval": variant.get("construction_interval"), "attributes_complete": complete}


def _candidate_revision(candidate):
    # JSON cannot sort mixed numeric/string keys throughout a mixed contract.
    return digest({**candidate, "specs": {field: sorted(values.items()) for field, values in candidate["specs"].items()}})


def _eligible(evidence, candidate):
    return "mismatch" not in policy.compare(evidence, candidate).values()


def _model_pages(adapter, maker, selected_model, model_after=0):
    after = selected_model - 1 if selected_model else model_after
    models = []
    for _ in range(3):
        page = directory.source_page("models", source_id=maker["manufacturer_id"],
                                     kind=maker["kind"], after=after, adapter=adapter)
        if selected_model:
            return [row for row in page["items"] if row["id"] == selected_model], None
        models.extend(page["items"])
        after = page["next_after"]
        if after is None:
            return models, None
    return models, after


def search(adapter, context, clarifications, who, *, selected_maker=None, selected_model=None, after=0, model_after=0):
    evidence = effective_evidence(context, clarifications)
    review = [field for field, observation in evidence.items() if observation["confidence"] == "conflict"]
    make = evidence.get("manufacturer", {}).get("reported")
    if not make or not evidence.get("manufacturer", {}).get("value"):
        return dict(items=[], models=[], questions=[], review=review, search_complete=False,
                    status="manufacturer_required", next_after=None, automatic=None)
    model_rows = []
    next_after = None
    directory_rows = []
    model_cursors = []
    unavailable = False
    with ThreadPoolExecutor(max_workers=8) as executor:
        all_makers = directory.manufacturer_choices(make, adapter)
        makers = [maker for maker in all_makers["items"] if not selected_maker or f'{maker["kind"]}:{maker["manufacturer_id"]}' == selected_maker]
        complete = not all_makers["partial"] and not selected_maker and len(makers) <= _MAX_MAKERS
        for maker in makers[_MAX_MAKERS:]:
            model_cursors.append({"maker": f'{maker["kind"]}:{maker["manufacturer_id"]}',
                                  "after": 0, "kind": maker["kind"]})
        makers = makers[:_MAX_MAKERS]
        for maker, future in zip(makers, [executor.submit(_model_pages, adapter, maker, selected_model, model_after) for maker in makers]):
            try:
                models, model_cursor = future.result()
            except HTTPException as error:
                if error.status_code != 503:
                    raise
                unavailable, complete = True, False
                continue
            if model_cursor is not None:
                complete = False
                model_cursors.append({"maker": f'{maker["kind"]}:{maker["manufacturer_id"]}',
                                      "after": model_cursor, "kind": maker["kind"]})
            model_rows.extend((maker, model) for model in models)
        model_rows = [pair for pair in model_rows if _eligible(evidence, _model_facts(*pair))]
        model_rows.sort(key=lambda pair: (
            policy.compare(evidence, _model_facts(*pair)).get("model") != "compatible",
            policy.compare(evidence, _model_facts(*pair)).get("year") != "compatible",
            policy.compare(evidence, _model_facts(*pair)).get("vehicle_type") == "mismatch",
            pair[1]["id"],
        ))
        complete &= len(model_rows) <= _MAX_MODELS
        scanned_models = model_rows[:_MAX_MODELS]
        futures = [executor.submit(directory.source_page, "modifications", source_id=model["id"],
                   kind=maker["kind"], after=after, adapter=adapter) for maker, model in scanned_models]
        for (maker, model), future in zip(scanned_models, futures):
            try:
                page = future.result()
            except HTTPException as error:
                if error.status_code != 503:
                    raise
                unavailable, complete = True, False
                continue
            cursor = page["next_after"]
            if selected_model:
                next_after = cursor
            complete &= cursor is None
            for variant in page["items"]:
                directory_rows.append((maker, model, variant))
        complete &= len(directory_rows) <= _MAX_VARIANTS
        # A scoped page is fully evaluated before filtering; global search remains bounded.
        candidates = list(executor.map(lambda row: _candidate(adapter, *row), directory_rows if selected_model else directory_rows[:_MAX_VARIANTS]))
    complete &= all(candidate["attributes_complete"] for candidate in candidates)
    def rank(candidate):
        matches = policy.compare(evidence, candidate)
        values = list(matches.values())
        return (matches.get("model") != "compatible", matches.get("model") == "mismatch",
                matches.get("year") == "mismatch", values.count("mismatch"), -values.count("compatible"))

    candidates = [candidate for candidate in candidates if _eligible(evidence, candidate)]
    candidates.sort(key=rank)
    answers = clarifications.answers
    status = ("complete" if complete
              else "unavailable" if unavailable and not candidates else "incomplete")
    revision = digest(evidence)
    items = []
    for candidate in candidates:
        locator = {field: candidate[field] for field in ("kind", "manufacturer_id", "model_id", "source_modification_id")}
        token = _sign("choice", {"locator": locator, "snapshot": _candidate_revision(candidate),
                                 "evidence": revision, "vin": context["vin"]}, who)
        items.append({**locator, **{field: candidate[field] for field in (
            "model", "manufacturer", "modification", "construction_interval", "attributes_complete")},
            "matches": policy.compare(evidence, candidate), "choice": token})
    auto = None
    if complete and len(items) == 1 and not review and not clarifications.model_correction and not clarifications.answers:
        matches = items[0]["matches"]
        technical = set(policy.TECHNICAL) - {"generation", "doors", "transmission_speeds", "engine_cylinders"}
        supported = sum(matches.get(field) == "compatible" and evidence[field]["confidence"] == "reported"
                        for field in technical if field in evidence)
        if "mismatch" not in matches.values() and matches.get("model") == "compatible" and matches.get("year") == "compatible" and supported >= 2:
            auto = items[0]["choice"]
    return dict(items=items, models=[{**_locator(maker, model, {"id": 0}), "model": model["name"],
                                    "construction_interval": model.get("construction_interval")}
                                   for maker, model in model_rows],
                questions=policy.needed_questions(evidence, candidates, answers), review=review,
                search_complete=complete, next_after=next_after, model_cursors=model_cursors, status=status, automatic=auto)


def selected_candidate(adapter, context, clarifications, token, who):
    signed = _read("choice", token, who, 1800)
    evidence = effective_evidence(context, clarifications)
    if signed["vin"] != context["vin"] or signed["evidence"] != digest(evidence):
        raise HTTPException(409, "Характеристики змінилися. Повторіть вибір модифікації")
    locator = signed["locator"]
    make = evidence.get("manufacturer", {}).get("reported") or ""
    makers = directory.manufacturer_choices(make, adapter, kinds=(locator["kind"],))
    maker = next((row for row in makers["items"] if all(row[field] == locator[field]
                 for field in ("kind", "manufacturer_id"))), None)
    if not maker and makers["partial"]:
        raise HTTPException(503, "Не вдалося підтвердити виробника в довіднику")
    models, _ = _model_pages(adapter, maker, locator["model_id"]) if maker else ([], False)
    model = models[0] if models else None
    if not model:
        raise HTTPException(409, "Обрану модель більше не знайдено")
    page = directory.source_page("modifications", source_id=model["id"], kind=maker["kind"],
        after=locator["source_modification_id"] - 1, adapter=adapter)
    variant = next((row for row in page["items"] if row["id"] == locator["source_modification_id"]), None)
    if not variant:
        raise HTTPException(409, "Обрану модифікацію більше не знайдено")
    candidate = _candidate(adapter, maker, model, variant)
    if signed["snapshot"] != _candidate_revision(candidate):
        if not candidate["attributes_complete"]:
            raise HTTPException(503, "Дані модифікації тимчасово недоступні")
        raise HTTPException(409, "Дані модифікації змінилися. Повторіть вибір")
    if not _eligible(evidence, candidate):
        raise HTTPException(409, "Модифікація суперечить характеристикам VIN. Уточніть дані та повторіть вибір")
    return candidate, evidence


def vehicle_details(context, evidence):
    original = context["details"]
    decoded = original.get("vehicle", {})
    characteristics = {**decoded, **{field: item["reported"] if item["value"] is not None else None
                                     for field, item in evidence.items()}}
    return dict(
        source=original.get("source") or "server_vin_resolution", observed_at=original.get("observed_at") or "",
        decoded=decoded, field_sources=original.get("field_sources") or {},
        conflicts=original.get("conflicts") or {}, consistency_issues=original.get("consistency_issues") or {},
        diagnostics=original.get("diagnostics") or {}, additional=original.get("additional") or {},
        decoded_additional=original.get("additional") or {}, characteristics=characteristics,
        trust="server_vin_report_with_operator_review",
    )


def validate_vehicle_fields(values, evidence):
    for field in ("manufacturer", "model", "generation", "year", "fuel_type", "engine_code",
                  "engine_displacement_l", "transmission", "drive_type"):
        supplied = values.get(field)
        observation = evidence.get(field)
        actual = _value(field, supplied)
        if not observation or observation["value"] is None:
            continue
        expected = observation["value"]
        if actual is None and supplied in (None, ""):
            continue
        matched = (policy.model_relation(actual, expected) == "compatible" if field == "model"
                   else actual is not None and policy.equivalent(field, actual, expected))
        if not matched:
            raise HTTPException(409, "Дані автомобіля змінилися. Підтвердьте актуальні уточнення VIN")


def validate_saved_evidence(vehicle, entry):
    details = vehicle.vin_details or {}
    if details.get("trust") != "server_vin_report_with_operator_review":
        return
    specs = policy.source_specs(entry.get("specifications") or [])
    specs["manufacturer"] = {policy.normalized("manufacturer", entry["manufacturer"]): entry["manufacturer"]}
    if entry.get("generation"):
        specs["generation"] = {policy.normalized("generation", entry["generation"]): entry["generation"]}
    modification = entry["modification"]
    period = policy.interval(modification.get("constructioninterval") or modification.get("construction_interval"))
    typed_years = tuple(entry.get(key) if type(entry.get(key)) is int else None for key in ("year_from", "year_to"))
    candidate = {"model": entry["model"], "model_period": typed_years, "variant_period": period, "specs": specs}
    evidence = {field: {"value": _value(field, value), "reported": value}
                for field, value in details.get("characteristics", {}).items()
                if field in policy.FIELDS and field != "engine_power_hp"}
    if not _eligible(evidence, candidate):
        raise HTTPException(409, "Модифікація суперечить збереженим характеристикам VIN")


def source_identity(candidate, readiness, *, allow_upgrade):
    return {**{field: candidate[field] for field in ("kind", "manufacturer_id", "model_id",
             "source_modification_id", "model", "modification", "construction_interval")},
            "source": "oracle", "directory_snapshot": _candidate_revision(candidate),
            "confirmation": "user_selected_identity_only", "vin_fitment_verified": False,
            "parts_graph_verified": readiness in ("exact", "partial"),
            "catalogue_readiness": readiness, "allow_upgrade": allow_upgrade}


def graph_plan(adapter, identity):
    requested = {field: identity[field] for field in ("kind", "manufacturer_id", "model_id")}
    requested["car_id"] = identity["source_modification_id"]
    try:
        reply = adapter.get("global:vehicles/source-graph", requested)
        if reply["identity"] != requested:
            raise catalogue.CatalogueUnavailable("invalid_identity")
        status = reply["status"]
        if status in ("absent", "unsupported", "unverified", "identity_mismatch"):
            return status, None
        if status != "available" or requested["kind"] != "passenger" or reply["source_scope"] != "passenger_prd_article_oem":
            raise catalogue.CatalogueUnavailable("invalid_scope")
        payload = catalogue.checked_plan(reply["plan"])
        if any(payload[field] != requested[field] for field in ("car_id", "manufacturer_id", "model_id")):
            raise catalogue.CatalogueUnavailable("invalid_identity")
        linked = [row for row in payload["categories"]
                  if row.get("source_fitment_linked") is True and row.get("article_count", 0) > 0
                  and row.get("kind") != "equipment"]
        if not linked:
            return "unverified", None
        exact = (payload.get("coverage") == "complete_verified" and payload.get("coverage_verified") is True
                 and payload.get("taxonomy_status") == "reviewed" and len(linked) == len(payload["categories"]))
        if not exact:
            payload = {**payload, "categories": linked, "coverage": "partial", "coverage_verified": False}
        return "exact" if exact else "partial", {"payload": payload, "sha256": digest(payload)}
    except (catalogue.CatalogueUnavailable, KeyError, TypeError, AttributeError):
        return "unavailable", None


def graph_preview(adapter, candidate):
    return graph_plan(adapter, candidate)


def persist_graph(db, vehicle, envelope, *, readiness):
    from app.services.dismantling_plan_v3 import generator_basis

    payload = envelope["payload"]
    state = vehicle.dismantling_v3
    vehicle.dismantling_v3 = {
        **state,
        "oracle_vehicle_identity": {**state["oracle_vehicle_identity"], "parts_graph_verified": True,
                                    "catalogue_readiness": readiness},
        "global_selection": dict(
            car_id=payload["car_id"], model_id=payload["model_id"],
            manufacturer_id=payload["manufacturer_id"], source_snapshot_sha=payload["source_snapshot_sha"],
            modification_description=state["oracle_vehicle_identity"]["modification"],
            vehicle_basis=catalogue.vehicle_basis(vehicle), identity_fingerprint=generator_basis(vehicle),
            confirmation="oracle_source_identity", vin_verified=False,
        ),
    }
    return catalogue.persist(db, vehicle, envelope, allow_partial=readiness != "exact")
