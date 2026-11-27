"""Offline resolution, persistence and tenant boundaries using source contract fixtures."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import DismantlingItem, Part, Vehicle
from app.schemas import VinClarifications
from app.services import auto_oem, unified_catalogue, vin_lookup, vin_resolution as resolution
from app.services.catalogue_format import digest
from app.services.vin_resolution_policy import interval, model_relation, normalized, year_relation

VIN = "WBAAAAAAAAAAAAA01"
MAKE = "Aster Mobility"
DRAFT = {"manufacturer": MAKE, "model": "3 Series", "year": 2015, "body_class": "Sedan",
         "fuel_type": "Diesel", "engine_displacement_l": "1995 cm³", "transmission": "6-speed manual"}
ORACLE = {"kind": "passenger", "manufacturer_id": 840, "model_id": 701, "source_modification_id": 900}
SHA = "a" * 64


class Source:
    def __init__(self):
        self.makers = {"passenger": [{"id": 840, "name": MAKE}], "commercial": []}
        self.models = [{"id": 700, "name": "3 (E30)", "construction_interval": "1982 - 1994"},
                       {"id": 701, "name": "3 (F30)", "construction_interval": "2011/10 - 2018/10"},
                       {"id": 702, "name": "30 Series", "construction_interval": "2010 - 2020"}]
        self.variants = {701: [
            {"id": 900, "model_id": 701, "name": "L", "construction_interval": "2014 - 2018"},
            {"id": 901, "model_id": 701, "name": "P", "construction_interval": "2014 - 2018"},
        ]}
        self.attributes = {
            900: [("Body Type", "Saloon"), ("Fuel Type", "Diesel"), ("Capacity (cc)", "1995"),
                  ("Gearbox Type", "Manual"), ("Drive Type", "FWD")],
            901: [("Body Type", "Saloon"), ("Fuel Type", "Petrol"), ("Capacity (cc)", "1995"),
                  ("Gearbox Type", "Manual"), ("Drive Type", "AWD")],
        }
        self.graph_status = "partial"
        self.snapshot = SHA
        self.calls = []
        self.outage = set()
        self.truncated = set()

    def get(self, path, params):
        endpoint = path.split("/")[-1]
        self.calls.append((endpoint, dict(params)))
        if endpoint in self.outage:
            raise unified_catalogue.CatalogueUnavailable("fixture")
        kind = params["kind"]
        if endpoint == "source-graph":
            if self.graph_status == "unavailable":
                raise unified_catalogue.CatalogueUnavailable("fixture")
            if self.graph_status != "partial":
                return {"identity": params, "status": self.graph_status}
            payload = {
                "schema": "carpot.vehicle.plan.v1", "manufacturer_id": params["manufacturer_id"],
                "car_id": params["car_id"], "model_id": params["model_id"], "coverage": "partial",
                "coverage_verified": False, "taxonomy_status": "unreviewed",
                "modification": {"description": "Synthetic graph"},
                "observed_at": "2026-01-01T00:00:00Z", "source_snapshot_sha": self.snapshot,
                "categories": [{"product_id": 41, "kind": "part", "name_source": "Synthetic engine",
                                "article_count": 1, "source_fitment_linked": True},
                               {"product_id": 42, "kind": "part", "name_source": "Unverified component",
                                "article_count": 0}],
            }
            return {"identity": params, "status": "available", "source_scope": "passenger_prd_article_oem",
                    "plan": {"payload": payload, "sha256": digest(payload)}}
        if endpoint in ("manufacturers", "manufacturer-directory"):
            rows = [row for row in self.makers[kind] if row["name"].casefold().startswith(params["name"].casefold())]
        elif endpoint == "models":
            rows = self.models
        elif endpoint == "modifications":
            rows = self.variants.get(params["model_id"], [])
        elif endpoint == "attributes":
            rows = [dict(attribute_type=key, display_value=value)
                    for key, value in self.attributes.get(params["car_id"], [])]
        else:
            pytest.fail(path)
        rows = [r for r in rows if r.get("id", 1) > params.get("after", 0)]
        page = rows[:params.get("limit", 50)]
        truncated = len(rows) > len(page) or endpoint in self.truncated
        return dict(source="oracle", kind=kind, vehicle_identity_only=True, fitment_verified=False,
                    items=page, next_after=page[-1]["id"] if endpoint in ("models", "modifications", "manufacturer-directory") and truncated else None,
                    truncated=truncated, source_modification_id=params.get("car_id"))


@pytest.fixture
def source(monkeypatch):
    provider = Source()
    monkeypatch.setattr(unified_catalogue.CatalogueAdapter, "get",
                        lambda self, path, params: provider.get(path, params))
    return provider


def who():
    return SimpleNamespace(workspace_account_id="warehouse", actor_id="actor",
                           session=SimpleNamespace(token_hash="session"))


def decoded(vin=VIN, **changes):
    return dict(vin=vin, vehicle={**DRAFT, **changes}, source="offline provider",
                field_sources={"manufacturer": "offline provider"}, observed_at="2026-01-01T00:00:00Z")


def context(identity, result=None):
    return resolution.trusted_context(resolution.issue_context(result or decoded(), identity), identity)


def lookup_context(logged, monkeypatch, result=None):
    calls = []

    def lookup(vin, *, public_only=False):
        assert public_only is True
        calls.append(vin)
        return result or decoded(vin)

    monkeypatch.setattr(vin_lookup, "lookup", lookup)
    response = logged.get("/api/v1/vehicles/vin/decode", params={"vin": VIN})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["resolution_context"], calls


def test_ranks_numeric_series_without_hiding_models_or_requesting_graph(source):
    identity = who()
    page = resolution.search(source, context(identity), VinClarifications(), identity)
    assert page["search_complete"] is True
    assert [row["source_modification_id"] for row in page["items"]] == [900]
    assert {row["model_id"] for row in page["models"]} == {701}
    assert page["models"][0]["model_id"] == 701
    assert page["automatic"] == page["items"][0]["choice"]
    assert {endpoint for endpoint, _ in source.calls} == {"manufacturers", "models", "modifications", "attributes"}


def test_decoder_engine_code_resolves_volvo_despite_a_noncritical_doors_conflict(source):
    source.makers = {"passenger": [{"id": 120, "name": "VOLVO"}], "commercial": []}
    source.models = [dict(id=index, name=f"Unrelated {index}", construction_interval="2001 -")
                     for index in range(1, 6)]
    source.models.append(dict(id=13084, name="XC90 II", construction_interval="09.2014 -"))
    source.variants = {13084: [
        dict(id=107555, model_id=13084, name="T6 AWD", construction_interval="09.2014 -"),
        dict(id=111864, model_id=13084, name="T8 Hybrid AWD", construction_interval="06.2015 -"),
    ]}
    specs = [("Power", "235 kW"), ("Capacity_Technical", "1969 ccm"), ("DriveType", "Привод на все колеса")]
    source.attributes = {
        107555: [*specs, ("EngineCode", "B 4204 T27"), ("FuelType", "бензин")],
        111864: [*specs, ("EngineCode", "B 4204 T35"), ("FuelType", "hybrid")],
    }
    report = decoded(vin="YV4A22PK2G1092943")
    report["vehicle"] = dict(manufacturer="VOLVO", model="XC90", year=2016, engine="B4204T27",
                             fuel_type="Бензин", engine_displacement_l="2", engine_power_hp="316",
                             vehicle_type="Багатоцільовий пасажирський автомобіль (MPV)")
    report["conflicts"] = {"doors": {"primary": "4", "secondary": "5"}}
    identity = who()
    ctx = context(identity, report)
    page = resolution.search(source, ctx, VinClarifications(), identity)
    assert [item["source_modification_id"] for item in page["items"]] == [107555]
    assert page["automatic"] == page["items"][0]["choice"]
    assert page["review"] == ["doors"] and page["questions"] == []
    assert {params["model_id"] for endpoint, params in source.calls if endpoint == "modifications"} == {13084}
    candidate, evidence = resolution.selected_candidate(source, ctx, VinClarifications(), page["automatic"], identity)
    assert candidate["modification"] == "T6 AWD" and evidence["engine_code"]["value"] == "b4204t27"
    report["vehicle"].pop("year")
    page = resolution.search(source, context(identity, report), VinClarifications(), identity)
    assert page["automatic"] == page["items"][0]["choice"]
    report["vehicle"]["engine"] = "2.0L I4"
    assert "engine_code" not in resolution.effective_evidence(context(identity, report), VinClarifications())


@pytest.mark.parametrize("kind,make,model,variant,power,displacement,start,year", [
    ("passenger", "BMW", "3 (E30)", 21, "73 kW", "1596 ccm", 1987, 1990),
    ("commercial", "DAF", "XF 105", 8387, "340 kW", "12900 ccm", 2005, 2010),
])
def test_model_year_and_source_technical_facts_can_resolve_passenger_and_truck(
        source, kind, make, model, variant, power, displacement, start, year):
    source.makers = {"passenger": [], "commercial": []}
    source.makers[kind] = [{"id": 840, "name": make}]
    source.models = [dict(id=701, name=model, construction_interval=f"{start} -")]
    source.variants[701] = [dict(id=id_, model_id=701, name=f"Test variant {id_}", construction_interval=f"{start} -")
                            for id_ in (variant, variant + 1)]
    source.attributes = {
        variant: [("Power", power), ("Capacity_Technical", displacement)],
        variant + 1: [("Power", "100 kW"), ("Capacity_Technical", displacement)],
    }
    identity = who()
    report = decoded()
    report["vehicle"] = dict(manufacturer=make, model=model, year=year, vehicle_type=kind,
                             engine_power_kw=power, engine_displacement_l=displacement)
    ctx = context(identity, report)
    page = resolution.search(source, ctx, VinClarifications(), identity)
    assert page["automatic"] == page["items"][0]["choice"]
    assert page["items"][0]["source_modification_id"] == variant
    assert page["questions"] == []
    report["vehicle"].pop("engine_power_kw")
    ambiguous = resolution.search(source, context(identity, report), VinClarifications(), identity)
    assert ambiguous["automatic"] is None
    assert [question["field"] for question in ambiguous["questions"]] == ["engine_power_kw"]


def test_reported_hyphenated_engine_code_is_not_asked_again(source):
    source.makers = {"passenger": [{"id": 111, "name": "TOYOTA"}], "commercial": []}
    source.models = [dict(id=3985, name="LAND CRUISER (_J6_)", construction_interval="1980 - 1991")]
    source.variants = {3985: [
        dict(id=9281, model_id=3985, name="4.0 (FJ62_G)", construction_interval="1987 - 1990"),
        dict(id=30632, model_id=3985, name="4.0 4x4", construction_interval="1987 - 1990"),
    ]}
    source.attributes = {
        9281: [("EngineCode", "3F-E"), ("FuelType", "Бензин"), ("Capacity_Technical", "3955 ccm")],
        30632: [("EngineCode", "3F"), ("FuelType", "Бензин"), ("Capacity_Technical", "3955 ccm")],
    }
    identity = who()
    report = decoded()
    report["vehicle"] = dict(manufacturer="TOYOTA", model="Land Cruiser", year=1989,
                             engine="3F-E", fuel_type="Бензин", engine_displacement_l="3.955")
    page = resolution.search(source, context(identity, report), VinClarifications(), identity)
    assert [item["source_modification_id"] for item in page["items"]] == [9281]
    assert page["automatic"] == page["items"][0]["choice"] and page["questions"] == []


@pytest.mark.parametrize("field,conflicting", [
    ("body_class", "coupe"), ("fuel_type", "electric"), ("engine_displacement_l", "2995 cc"),
    ("transmission", "automatic"), ("drive_type", "RWD"), ("year", 2025), ("generation", "F20"),
    ("engine_power_kw", "290"), ("engine_power_hp", "400"), ("engine_code", "ZY99"),
])
def test_conflicting_facts_are_ranked_and_old_tokens_are_rejected(source, field, conflicting):
    source.attributes[900].extend([("Engine Code", "AX42"), ("Power (kW)", "135"), ("Generation", "F30")])
    identity = who()
    ctx = context(identity)
    page = resolution.search(source, ctx, VinClarifications(), identity)
    ticket = page["items"][0]["choice"]
    changed = context(identity, decoded(**{field: conflicting}))
    result = resolution.search(source, changed, VinClarifications(), identity)
    assert all(row["source_modification_id"] != 900 for row in result["items"])
    with pytest.raises(HTTPException, match="Характеристики змінилися") as error:
        resolution.selected_candidate(source, changed, VinClarifications(), ticket, identity)
    assert error.value.status_code == 409


def test_variant_questions_only_for_relevant_unknowns_and_missing_facts_stay_unknown(source):
    identity = who()
    source.attributes[901] = [("Body Type", "Sedan"), ("Fuel Type", "Diesel"), ("Drive Type", "AWD")]
    ctx = context(identity)
    page = resolution.search(source, ctx, VinClarifications(), identity)
    assert [question["field"] for question in page["questions"]] == ["drive_type"]
    assert page["automatic"] is None
    assert page["items"][1]["matches"]["engine_displacement_l"] == "unknown"
    clarifications = VinClarifications(answers={"drive_type": "FWD"})
    result = resolution.search(source, ctx, clarifications, identity)
    assert [row["source_modification_id"] for row in result["items"]] == [900]
    assert result["questions"] == []
    result = resolution.search(source, ctx, VinClarifications(answers={"drive_type": None}), identity)
    assert len(result["items"]) == 2 and result["automatic"] is None and not result["questions"]


def test_truncated_attributes_and_outage_are_not_an_empty_directory(source):
    identity = who()
    ctx = context(identity)
    source.truncated.add("attributes")
    result = resolution.search(source, ctx, VinClarifications(), identity)
    assert result["status"] == "incomplete" and result["automatic"] is None
    assert resolution.graph_preview(source, {**ORACLE, "attributes_complete": False})[0] == "partial"
    source.outage.add("modifications")
    assert resolution.search(source, ctx, VinClarifications(), identity)["status"] == "unavailable"
    source.outage.add("manufacturers")
    with pytest.raises(HTTPException) as error:
        resolution.search(source, ctx, VinClarifications(), identity)
    assert error.value.status_code == 503


def test_scoped_variant_paging_resumes_at_last_consumed_id(source):
    identity = who()
    source.variants[701] = [dict(id=index, model_id=701, name=str(index), construction_interval="2014 - 2018")
                            for index in range(900, 951)]
    # Explicitly place incompatible rows on both sides of the source page boundary.
    source.attributes = {
        index: [("Fuel Type", "Petrol" if index in (901, 949, 950) else "Diesel"),
                ("Body Type", "Saloon")]
        for index in range(900, 951)
    }
    # Include a compatible late row after an entirely filtered page.
    source.variants[701].extend(
        dict(id=index, model_id=701, name=str(index), construction_interval="2014 - 2018")
        for index in range(951, 1001))
    source.attributes.update({
        index: [("Fuel Type", "Diesel" if index == 1000 else "Petrol")]
        for index in range(951, 1001)
    })
    after = 0
    seen = []
    cursors = []
    for _ in range(3):
        page = resolution.search(source, context(identity), VinClarifications(), identity,
                                 selected_maker="passenger:840", selected_model=701, after=after)
        assert not page["search_complete"] and page["automatic"] is None
        assert all("mismatch" not in row["matches"].values() for row in page["items"])
        if after == 949:
            assert page["items"] == []  # an empty filtered page must preserve the source cursor
        seen.extend(row["source_modification_id"] for row in page["items"])
        after = page["next_after"]
        cursors.append(after)
    assert cursors == [949, 999, None]
    assert sorted(seen) == [index for index in range(900, 949) if index != 901] + [1000]



def test_context_rejects_expiry_tampering_tenant_and_vin(source, monkeypatch):
    identity = who()
    token = resolution.issue_context(decoded(), identity)
    other = who()
    other.workspace_account_id = "elsewhere"
    for signed, user, vin in [(token + "0", identity, VIN), (token, other, VIN),
                              (token, identity, "WBAAAAAAAAAAAAA02")]:
        with pytest.raises(HTTPException) as error:
            resolution.trusted_context(signed, user, vin)
        assert error.value.status_code == 409
    now = resolution.time.time()
    monkeypatch.setattr(resolution.time, "time", lambda: now + 1900)
    with pytest.raises(HTTPException, match="застарів"):
        resolution.trusted_context(token, identity, VIN)


def test_review_can_correct_generic_model_without_replacing_original_evidence(source):
    identity = who()
    report = decoded(model="Generic chassis")
    report["conflicts"] = {"fuel_type": {"primary": "Diesel", "secondary": "Petrol"}}
    ctx = context(identity, report)
    initial = resolution.search(source, ctx, VinClarifications(), identity)
    assert initial["review"] == ["fuel_type"] and initial["automatic"] is None
    resolution.selected_candidate(source, ctx, VinClarifications(), initial["items"][0]["choice"], identity)
    reviewed = VinClarifications(answers={"fuel_type": "Diesel"}, model_correction="3 Series")
    page = resolution.search(source, ctx, reviewed, identity)
    candidate, evidence = resolution.selected_candidate(source, ctx, reviewed, page["items"][0]["choice"], identity)
    assert candidate["source_modification_id"] == 900 and page["automatic"] == page["items"][0]["choice"]
    assert resolution.vehicle_details(ctx, evidence)["decoded"]["model"] == "Generic chassis"
    corrected = resolution.effective_evidence(context(identity), VinClarifications(model_correction="30 Series"))
    assert corrected["model"]["value"] == "30 Series"


@pytest.mark.parametrize("status", ["absent", "unavailable", "unverified", "identity_mismatch", "unsupported"])
def test_graph_states_keep_source_identity_separate(source, status):
    source.graph_status = status
    assert resolution.graph_plan(source, ORACLE) == (status, None)


def test_model_year_boundary_and_units():
    assert interval("10/2011 - 12/2018") == (2011, 2018)
    assert interval("201110–201812") == (2011, 2018)
    assert year_relation(2019, (2011, 2018)) == "unknown"
    assert year_relation(2020, (2011, 2018)) == "mismatch"
    assert model_relation("Серія 3", "3 (F30)") == "compatible"
    assert model_relation("X3", "X30") == "mismatch"
    assert model_relation("Model II", "Model III") == "mismatch"
    assert model_relation("3 (F30)", "3 (F31)") == "mismatch"
    assert normalized("engine_displacement_l", "1995 см³") == 1.995
    assert normalized("transmission", "6-ступенева механічна") == "manual"


def test_post_rechecks_trust_snapshot_and_conflicting_client_values(logged, source, monkeypatch):
    token, calls = lookup_context(logged, monkeypatch)
    headers = {"X-Vin-Context": token}
    search = logged.get("/api/v1/vehicles/vin/resolution", headers=headers)
    assert search.status_code == 200, search.text
    choice = search.json()["items"][0]["choice"]
    graph = logged.get("/api/v1/vehicles/vin/resolution-graph",
                       headers={**headers, "X-Vin-Choice": choice})
    assert graph.json() == {"status": "partial", "source_snapshot_sha": SHA,
                            "counts": {"categories": 0, "positions": 1}}
    body = dict(manufacturer=MAKE, model="3 Series", vin=VIN, year=2015,
                vin_resolution={"context": token, "choice": choice, "graph_sha": SHA},
                vin_details={"decoded": {"fuel_type": "Petrol"}})
    assert logged.post("/api/v1/vehicles", json={**body, "fuel_type": "Petrol"}).status_code == 409
    assert logged.post("/api/v1/vehicles", json={**body, "vin_resolution": {
        **body["vin_resolution"], "clarifications": {"answers": {"drive_type": "RWD"}}}}).status_code == 409
    source.snapshot = "b" * 64
    assert logged.post("/api/v1/vehicles", json=body).status_code == 409
    source.snapshot = SHA
    source.attributes[900][1] = ("Fuel Type", "Petrol")
    assert logged.post("/api/v1/vehicles", json=body).status_code == 409
    source.attributes[900][1] = ("Fuel Type", "Diesel")
    saved = logged.post("/api/v1/vehicles", json=body)
    assert saved.status_code == 201, saved.text
    assert logged.post("/api/v1/vehicles", json=body).json()["detail"]["vehicle_id"] == saved.json()["id"]
    assert calls == [VIN]
    with Session(engine()) as db:
        donor = db.get(Vehicle, saved.json()["id"])
        assert donor.vin_details["decoded"]["fuel_type"] == "Diesel"
        assert donor.dismantling_v3["oracle_vehicle_identity"]["parts_graph_verified"] is True
        assert donor.dismantling_v3["global_selection"]["source_snapshot_sha"] == SHA
        assert len(donor.dismantling_v3["unified_catalogue"]["payload"]["categories"]) == 1
        assert db.scalar(select(func.count()).select_from(DismantlingItem)) == 1
        assert db.scalar(select(func.count()).select_from(Part)) == 0


def test_verified_later_graph_upgrade_uses_existing_writer_and_never_creates_stock(logged, source, monkeypatch):
    token, _ = lookup_context(logged, monkeypatch)
    search = logged.get("/api/v1/vehicles/vin/resolution", headers={"X-Vin-Context": token})
    choice = search.json()["items"][0]["choice"]
    source.graph_status = "absent"
    body = dict(manufacturer=MAKE, model="3 Series", vin=VIN, year=2015)
    assert logged.post("/api/v1/vehicles", json={**body,
        "vin_resolution": {"context": token}}).status_code == 422
    assert logged.post("/api/v1/vehicles", json={**body,
        "vin_resolution": {"context": token, "choice": choice}}).status_code == 422
    response = logged.post("/api/v1/vehicles", json=dict(manufacturer=MAKE, model="3 Series", vin=VIN, year=2015,
                           vin_resolution={"context": token, "choice": choice, "accept_base_catalogue": True}))
    assert response.status_code == 201, response.text
    vid = response.json()["id"]
    with Session(engine()) as db:
        donor = db.get(Vehicle, vid)
        assert donor.dismantling_v3["oracle_vehicle_identity"]["catalogue_readiness"] == "absent"
        account = donor.account_id
    source.graph_status = "partial"
    cache = auto_oem.SourceCache(source)
    monkeypatch.setattr(cache, "get_offer_batch", lambda *args: {})
    monkeypatch.setattr(cache, "get_offers", lambda *args: [])
    monkeypatch.setattr(cache, "plan", lambda *args: deepcopy(resolution.graph_plan(source, ORACLE)[1]["payload"]))
    monkeypatch.setattr(cache, "sibling_candidates", lambda *args: {})
    assert auto_oem.enrich_vehicle(engine(), "another-tenant", vid, cache) == 0
    auto_oem.enrich_vehicle(engine(), account, vid, cache)
    auto_oem.enrich_vehicle(engine(), account, vid, cache)
    with Session(engine()) as db:
        donor = db.get(Vehicle, vid)
        assert donor.dismantling_v3["oracle_vehicle_identity"]["catalogue_readiness"] == "partial"
        assert db.scalar(select(func.count()).select_from(DismantlingItem)) == 1
        assert db.scalar(select(func.count()).select_from(Part)) == 0


def test_unknown_year_question_appears_only_if_periods_differ(source):
    identity = who()
    source.attributes[901] = source.attributes[900]
    source.variants[701][1]["construction_interval"] = "2017 - 2018"
    result = resolution.search(source, context(identity, decoded(year=None)), VinClarifications(), identity)
    assert result["questions"] == [{"field": "year", "options": ["2018", "2017", "2016", "2015", "2014"]}]
    assert result["automatic"] is None


def test_normalizes_accented_and_punctuated_manufacturer_names():
    from app.services.vin_source_directory import manufacturer_choices

    class Manufacturer:
        def get(self, path, params):
            assert params["name"] == "Strom"
            return dict(source="oracle", kind=params["kind"], items=[{"id": 1, "name": "Strom & Co"}],
                        truncated=False, vehicle_identity_only=True, fitment_verified=False)

    result = manufacturer_choices("Ström & Co", Manufacturer(), kinds=("passenger",))
    assert result["items"] == [{"manufacturer_id": 1, "manufacturer": "Strom & Co", "kind": "passenger"}]


def test_graph_exact_requires_reviewed_coverage_and_authoritative_identity(source):
    underlying = source.get

    class Verified:
        def get(self, path, params):
            reply = underlying(path, params)
            payload = reply["plan"]["payload"]
            payload.update(coverage="complete_verified", coverage_verified=True, taxonomy_status="reviewed")
            payload["categories"] = [dict(payload["categories"][0], name_uk="Двигун",
                mapping_reviewed_by="fixture",
                category_path=["Двигун і системи", "Двигун у зборі та опори", "Двигун"])]
            reply["plan"]["sha256"] = digest(payload)
            return reply

    response = Verified().get("global:vehicles/source-graph", {"kind": "passenger",
        "manufacturer_id": 840, "model_id": 701, "car_id": 900})
    assert response["plan"]["payload"]["coverage_verified"] is True
    from app.services.catalogue_carpot_sections import SECTIONS, SUBCATEGORIES
    first_category, first_subcategory = SECTIONS[0], SUBCATEGORIES[0][0][0]
    payload = response["plan"]["payload"]
    payload["categories"][0]["category_path"] = [first_category, first_subcategory, "Двигун"]
    response["plan"]["sha256"] = digest(payload)
    adapter = SimpleNamespace(get=lambda *args: deepcopy(response))
    readiness, plan = resolution.graph_plan(adapter, ORACLE)
    assert readiness == "exact"
    assert plan["payload"]["source_snapshot_sha"] == SHA
    response["identity"]["kind"] = "commercial"
    assert resolution.graph_plan(adapter, ORACLE) == ("unavailable", None)



def test_stage13_manual_intake_does_not_trigger_legacy_automatic_plan(logged, source):
    response = logged.post("/api/v1/vehicles", json={
        "manufacturer": "Volvo", "model": "XC90 II", "year": 2016, "vin": "YV4A22PK2G1092943",
        "engine_code": "B4204T27", "fuel_type": "petrol", "drive_type": "AWD", "vin_intake_mode": "manual",
    })
    assert response.status_code == 201, response.text
    vid = response.json()["id"]
    with Session(engine()) as db:
        vehicle = db.get(Vehicle, vid)
        account = vehicle.account_id
        assert vehicle.dismantling_v3["vin_intake"] == "manual"
    assert auto_oem.enrich_vehicle(engine(), account, vid, auto_oem.SourceCache(source)) == 0
    assert source.calls == []
    base_path = f"/api/v1/vehicles/{vid}/unified-catalogue/base"
    assert logged.get(f"/api/v1/vehicles/{vid}/global-dismantling").json()["legacy"] is False
    first = logged.post(base_path)
    assert first.status_code == 200, first.text
    assert logged.post(base_path).json() == {"saved": True, "source": "base"}
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(DismantlingItem)) > 0
        assert db.scalar(select(func.count()).select_from(Part)) == 0


def test_concurrent_create_serializes_vin_under_account_lock(logged, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi import BackgroundTasks

    from app.api import routes
    from app.models import Account, Operation
    from app.schemas import VehicleInput

    with Session(engine()) as db:
        account_id = db.scalar(select(Account.id))
    actor = SimpleNamespace(workspace_account_id=account_id, actor_id=account_id)
    # HTTP authentication has its own workspace fence. Invoke the handler
    # with independent sessions to exercise the creation fence itself.
    ready = Barrier(2, timeout=10)
    allocate = routes.automatic_donor_id

    def concurrent_allocation(db, account_id):
        value = allocate(db, account_id)
        ready.wait()
        return value

    def create(vin):
        data = VehicleInput(manufacturer=MAKE, model="3 Series", year=2015,
                            vin=vin, vin_intake_mode="manual")
        with Session(engine()) as db:
            try:
                result = routes.vehicle_create(data, db, actor, BackgroundTasks())
            except HTTPException as error:
                return error.status_code, error.detail["vehicle_id"]
            return 201, result["id"]

    monkeypatch.setattr(routes, "automatic_donor_id", concurrent_allocation)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(create, (VIN, VIN.lower())))

    assert [status for status, _ in results] == [201, 409], results
    created = results[0][1]
    assert results[1][1] == created
    with Session(engine()) as db:
        assert db.scalars(select(Vehicle.id).where(Vehicle.vin == VIN)).all() == [created]
        assert db.scalar(select(func.count()).select_from(Operation).where(
            Operation.type == "vehicle_create", Operation.vehicle_id == created)) == 1


def test_model_pages_keep_late_models_reachable(source):
    identity = who()
    source.models = [{"id": index, "name": f"Line {index}"} for index in range(1, 158)]
    ctx = context(identity, decoded(model=None))
    initial = resolution.search(source, ctx, VinClarifications(), identity)
    assert initial["model_cursors"] == [{"maker": "passenger:840", "after": 150, "kind": "passenger"}]
    assert len(initial["models"]) == 150
    assert not initial["search_complete"] and initial["automatic"] is None
    tail = resolution.search(source, ctx, VinClarifications(), identity,
                             selected_maker="passenger:840", model_after=150)
    assert [row["model_id"] for row in tail["models"]] == list(range(151, 158))
    assert not tail["model_cursors"] and tail["automatic"] is None


def test_incomplete_scoped_search_asks_only_supported_clarifications(source):
    identity = who()
    source.attributes[901] = [("Body Type", "Sedan"), ("Fuel Type", "Diesel"), ("Drive Type", "AWD")]
    source.truncated.add("attributes")
    ctx = context(identity)
    scope = dict(selected_maker="passenger:840", selected_model=701)
    result = resolution.search(source, ctx, VinClarifications(), identity, **scope)
    assert not result["search_complete"] and result["automatic"] is None
    assert result["questions"] == [{"field": "drive_type", "options": ["FWD", "AWD"]}]
    clarified = resolution.search(source, ctx, VinClarifications(answers={"drive_type": "AWD"}), identity, **scope)
    assert [row["source_modification_id"] for row in clarified["items"]] == [901]
    assert clarified["questions"] == [] and clarified["automatic"] is None


def test_explicit_base_without_selected_modification(logged, source, monkeypatch):
    token, _ = lookup_context(logged, monkeypatch)
    body = dict(manufacturer=MAKE, model="3 Series", vin=VIN, year=2015,
                vin_resolution={"context": token, "accept_base_catalogue": True})
    response = logged.post("/api/v1/vehicles", json=body)
    assert response.status_code == 201, response.text
    with Session(engine()) as db:
        donor = db.get(Vehicle, response.json()["id"])
        assert donor.dismantling_v3["vin_intake"] == "reviewed"
        assert not donor.dismantling_v3.get("global_selection")


def test_vw_alias_keeps_regional_and_commercial_identities():
    from app.services.vin_source_directory import manufacturer_choices

    class RegionalDirectory:
        def get(self, path, query):
            rows = {
                ("passenger", "VW"): [{"id": 1, "name": "VW"}, {"id": 2, "name": "VW (USA)"},
                                       {"id": 3, "name": "VW Industrial"}],
                ("commercial", "Volkswagen"): [{"id": 1, "name": "Volkswagen"}],
            }
            return {"source": "oracle", "kind": query["kind"],
                    "vehicle_identity_only": True, "fitment_verified": False,
                    "items": rows.get((query["kind"], query["name"]), [])}

    matches = manufacturer_choices("Volkswagen", RegionalDirectory())
    assert {(r["kind"], r["manufacturer_id"]) for r in matches["items"]} == {
        ("passenger", 1), ("passenger", 2), ("commercial", 1),
    }


def test_selected_graph_adds_oem_before_explicit_receipt(logged, source, monkeypatch):
    token, _ = lookup_context(logged, monkeypatch)
    page = logged.get("/api/v1/vehicles/vin/resolution", headers={"X-Vin-Context": token}).json()
    result = logged.post("/api/v1/vehicles", json=dict(
        manufacturer=MAKE, model="3 Series", year=2015, vin=VIN, engine_displacement_l=2,
        vin_resolution={"context": token, "choice": page["items"][0]["choice"]}))
    assert result.status_code == 201, result.text
    donor = result.json()["id"]
    with Session(engine()) as db:
        account = db.get(Vehicle, donor).account_id
        assert db.scalar(select(func.count()).select_from(Part)) == 0

    cache = auto_oem.SourceCache(source)
    offers = [dict(supplier_id=7, article_nr="A-41", brand="Fixture", oem_numbers=["OEM-41"])]
    monkeypatch.setattr(cache, "plan", lambda *args: resolution.graph_plan(source, ORACLE)[1]["payload"])
    monkeypatch.setattr(cache, "get_offer_batch", lambda *args: {41: offers})
    monkeypatch.setattr(cache, "sibling_candidates", lambda *args: {})
    auto_oem.enrich_vehicle(engine(), account, donor, cache)
    base = f"/api/v1/vehicles/{donor}"
    plan = logged.get(base + "/global-dismantling").json()
    assert plan["selection"]["identity_fingerprint"] == plan["selection_basis"]
    assert plan["catalogue_oems"]["41"]["oem_number"] == "OEM-41"
    receipt = {"keys": [plan["keys"]["41"]], "confirm_physical_receipt": True}
    assert logged.post(base + "/unified-catalogue/stock", json=receipt).json() == {"added": 1, "skipped": 0}
    assert logged.post(base + "/unified-catalogue/stock", json=receipt).json() == {"added": 0, "skipped": 1}
    with Session(engine()) as db:
        part = db.scalar(select(Part))
        assert part.quantity == 1
        assert part.oem_number == "OEM-41"
        assert part.oem_provenance["physical_number_confirmed_by_user"] is False


def test_oracle_real_attribute_names_and_fuel_conflict():
    from app.services.vin_resolution_policy import source_specs, compare
    rows = [("FuelType", "Дизель"), ("EngineType", "Дизель"), ("EngineCode", "D 4204 T6"),
            ("Capacity_Technical", "1969 ccm"), ("Power", "140 kW"), ("Power", "190 PS"),
            ("DriveType", "Привод на все колеса")]
    specs = source_specs([dict(attribute_type=k, display_value=v) for k,v in rows])
    assert list(specs["fuel_type"]) == ["diesel"]
    assert list(specs["engine_displacement_l"]) == [1.969]
    assert list(specs["drive_type"]) == ["AWD"]
    assert "engine_power_kw" in specs
    assert compare({"fuel_type": {"value": "petrol"}}, {"specs": specs}) == {"fuel_type": "mismatch"}



def test_oracle_catalogue_intake_without_vin_keeps_oem_and_receives_once(logged, source):
    from uuid import uuid4

    original_get = source.get

    def live_graph(path, params):
        reply = original_get(path, params)
        if not path.endswith("source-graph"):
            return reply
        payload = reply["plan"]["payload"]
        article_graph = {"items": [[13, "Offer-1", "Supplier One", ["OE-1", "OE-2"]],
                                   [14, "Offer-2", "Supplier Two", ["OE-1"]]],
                         "product_links": {"41": [0, 1]}}
        payload.update(kind=params["kind"], article_graph_sha=digest(article_graph))
        payload["categories"][0]["article_count"] = 2
        return {**reply, "source_scope": "oracle_vehicle_prd_article_oem", "article_graph": article_graph,
                "counts": {"categories": 0, "positions": 2}, "plan": {"payload": payload, "sha256": digest(payload)}}

    source.makers["commercial"] = [{"id": 840, "name": MAKE}]
    source.get = live_graph
    request = {"intake_request_key": str(uuid4()), "vin_intake_mode": "catalogue",
               "source_identity": {**ORACLE, "kind": "commercial", "confirmed": True},
               "catalogue_graph_sha": SHA, "manufacturer": MAKE, "model": "3 (F30)", "year": 2015}
    response = logged.post("/api/v1/vehicles", json=request)
    assert response.status_code == 201, response.text
    vid = response.json()["id"]
    assert response.json()["vin"] is None
    replay = logged.post("/api/v1/vehicles", json=request)
    assert replay.status_code == 201 and replay.json()["id"] == vid
    assert logged.post("/api/v1/vehicles", json={**request, "year": 2016}).status_code == 409
    view = logged.get(f"/api/v1/vehicles/{vid}/global-dismantling").json()
    assert "article_graph" not in view["saved"]
    assert view["oems"]["41"]["oem_options"] == ["OE-1", "OE-2"]
    assert "42" not in view["oems"]
    key = view["keys"]["41"]
    offers = logged.get(f"/api/v1/vehicles/{vid}/unified-catalogue/articles", params={"key": key})
    assert [(offer["article_nr"], offer["oem_numbers"]) for offer in offers.json()["articles"]] == [
        ("Offer-1", ["OE-1", "OE-2"]), ("Offer-2", ["OE-1"])]
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part)) == 0
    endpoint = f"/api/v1/vehicles/{vid}/unified-catalogue/stock"
    receipt = {"keys": [key], "confirm_physical_receipt": True}
    assert logged.post(endpoint, json=receipt).json() == {"added": 1, "skipped": 0}
    assert logged.post(endpoint, json=receipt).json() == {"added": 0, "skipped": 1}
    with Session(engine()) as db:
        part = db.scalar(select(Part).where(Part.vehicle_id == vid))
        assert (part.quantity, part.oem_number) == (1, "OE-1")
        assert len(part.oem_provenance["alternatives"]) == 2


def test_manual_intake_requires_explicit_base_and_replays_without_vin(logged):
    from uuid import uuid4

    request = {"intake_request_key": str(uuid4()), "vin_intake_mode": "manual",
               "manufacturer": MAKE, "model": "Unknown model", "year": 2015}
    assert logged.post("/api/v1/vehicles", json=request).status_code == 422
    accepted = {**request, "accept_base_catalogue": True}
    response = logged.post("/api/v1/vehicles", json=accepted)
    assert response.status_code == 201, response.text
    vid = response.json()["id"]
    assert logged.post("/api/v1/vehicles", json=accepted).json()["id"] == vid
    with Session(engine()) as db:
        assert db.get(Vehicle, vid).dismantling_v3["unified_base"] is True
        assert db.scalar(select(func.count()).select_from(Part)) == 0



def test_later_oracle_selection_preserves_the_manual_plan(logged, source):
    from uuid import uuid4

    created = logged.post("/api/v1/vehicles", json={
        "intake_request_key": str(uuid4()), "vin_intake_mode": "manual",
        "accept_base_catalogue": True, "manufacturer": MAKE, "model": "3 Series", "year": 2015,
    })
    assert created.status_code == 201, created.text
    vid = created.json()["id"]
    with Session(engine()) as db:
        old_ids = set(db.scalars(select(DismantlingItem.id).where(DismantlingItem.vehicle_id == vid)))
    state = logged.get(f"/api/v1/vehicles/{vid}/global-dismantling").json()
    body = {"identity": {**ORACLE, "confirmed": True}, "manufacturer": MAKE, "model": "3 (F30)",
            "source_snapshot_sha": SHA, "expected_basis": state["selection_basis"]}
    path = f"/api/v1/vehicles/{vid}/oracle-catalogue-selection"
    attached = logged.post(path, json=body)
    assert attached.status_code == 200, attached.text
    assert attached.json()["dismantling_v3"]["legacy_base_plan"] is True
    assert logged.post(path, json=body).status_code == 200
    with Session(engine()) as db:
        now_ids = set(db.scalars(select(DismantlingItem.id).where(DismantlingItem.vehicle_id == vid)))
        assert old_ids < now_ids and len(now_ids - old_ids) == 1
    legacy = logged.get(f"/api/v1/vehicles/{vid}/dismantling-workspace", params={"source": "base"})
    assert legacy.status_code == 200, legacy.text
    assert {item["key"].removeprefix("base:") for item in legacy.json()["items"]} == old_ids
