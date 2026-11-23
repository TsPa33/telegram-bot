"""Stage 12 universal source matching: synthetic, offline, no paid provider calls."""
import pytest
from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.db import engine
from app.models import Vehicle, DismantlingItem, Part
from app.services import vin_catalogue_matching as matching
from app.services import unified_catalogue as catalogue

SHA = "a" * 64


def directory_entry(make="DAF", model="XF", car_id=430001, mid=9300, maker_id=144):
    return dict(source_modification_id=car_id, manufacturer_id=maker_id, model_id=mid,
                manufacturer=make, model=model, generation="",
                modification=dict(description="12.9 Euro 6"), snapshot_sha=SHA,
                coverage="partial", type_count=1, specifications=[], article_count=1)


def source_plan(entry):
    return dict(sha256=SHA, payload=dict(
        schema="carpot.vehicle.plan.v1", manufacturer_id=entry["manufacturer_id"],
        model_id=entry["model_id"], car_id=entry["source_modification_id"],
        source_snapshot_sha=entry["snapshot_sha"], modification=dict(id=entry["source_modification_id"],
        description=entry["modification"]["description"]),
        observed_at="2026-11-23T06:00:00+00:00", coverage="partial",
        coverage_verified=False, taxonomy_status="unreviewed",
        categories=[dict(product_id=42, name_source="Source engine", name_uk="Двигун",
                          kind="review", article_count=1, category_path=[],
                          source_fitment_linked=True)]
    ))


class Source:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def directory(self, after=0, car_id=None, **filters):
        self.calls.append(dict(after=after, car_id=car_id, **filters))
        if car_id is not None:
            return dict(items=[r for r in self.rows if r["source_modification_id"] == car_id], next_after=None)
        rows = [r for r in self.rows if r["source_modification_id"] > after]
        return dict(items=rows, next_after=None)
    def plan(self, car_id, *, global_source=False):
        assert global_source
        return source_plan(next(r for r in self.rows if r["source_modification_id"] == car_id))


@pytest.mark.parametrize("make,model", [("DAF", "XF"), ("MAN", "TGX"),
                                        ("BMW", "X5"), ("Volvo", "XC90 II")])
def test_generic_directory_matches_any_manufacturer(make, model):
    rows=[directory_entry(make,model),directory_entry("OTHER",model,car_id=430002)]
    result=matching.search_candidates(Source(rows),manufacturer=make,model=model)
    assert len(result["items"]) == 1
    assert result["items"][0]["model_matches"] is True
    assert result["items"][0]["vin_fitment_verified"] is False



def test_bounded_paging_does_not_skip_unconsumed_modifications():
    rows = [directory_entry("DAF","XF",car_id=1000+i) for i in range(92)]
    src = Source(rows)
    seen = []
    cursor = 0
    for _ in range(3):
        page = matching.search_candidates(src,manufacturer="DAF",model="XF",after=cursor,limit=40)
        seen.extend(r["source_modification_id"] for r in page["items"])
        if page["next_after"] is None:
            break
        cursor = page["next_after"]
    assert len(seen) == len(set(seen)) == 92
    assert seen == list(range(1000,1092))


def test_catalogue_does_not_accept_chassis_or_fuzzy_model_as_exact():
    assert not matching.same_model("FT", "XF")
    assert matching.same_model("XC90", "XC90 II")
    assert not matching.same_model("XF", "XFA")


def test_vin_model_must_be_explicitly_corrected_before_source_selection():
    entry=directory_entry()
    src=Source([entry])
    from types import SimpleNamespace
    selection=SimpleNamespace(source_modification_id=entry["source_modification_id"],
        model_id=entry["model_id"], manufacturer_id=entry["manufacturer_id"],
        source_snapshot_sha=SHA)
    with pytest.raises(HTTPException) as err:
        matching.validate_selection(src,selection=selection,manufacturer="DAF",model="FT")
    assert err.value.status_code == 409
    accepted, plan=matching.validate_selection(src,selection=selection,manufacturer="DAF",model="XF")
    assert accepted["source_modification_id"] == entry["source_modification_id"]
    assert plan["payload"]["car_id"] == entry["source_modification_id"]


@pytest.fixture
def mock_catalogue(monkeypatch):
    src=Source([directory_entry()])
    monkeypatch.setattr(catalogue.CatalogueAdapter,"directory",
                        lambda self,*args,**kwargs:src.directory(*args,**kwargs))
    monkeypatch.setattr(catalogue.CatalogueAdapter,"plan",
                        lambda self,*args,**kwargs:src.plan(*args,**kwargs))
    return src


def test_vin_catalogue_candidate_endpoint_is_read_only(logged, mock_catalogue):
    result=logged.get('/api/v1/vehicles/vin/catalogue-candidates?manufacturer=DAF&model=FT')
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["source_modification_id"] == 430001
    assert result.json()["items"][0]["model_matches"] is False
    assert result.json()["vin_fitment_verified"] is False


def test_vin_creation_pins_exact_source_plan_without_physical_stock(logged, mock_catalogue):
    source=mock_catalogue.rows[0]
    body=dict(manufacturer="DAF",model="XF",year=2014,engine="12.9 diesel",
              catalogue_selection=dict(source_modification_id=source["source_modification_id"],
                model_id=source["model_id"],manufacturer_id=source["manufacturer_id"],
                source_snapshot_sha=source["snapshot_sha"],confirmed=True))
    response=logged.post('/api/v1/vehicles',json=body)
    assert response.status_code == 201, response.text
    vehicle_id=response.json()["id"]
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle_id)
        state=v.dismantling_v3
        assert state["global_selection"]["confirmation"] == "user_selected"
        assert state["global_selection"]["vin_verified"] is False
        assert state["global_selection"]["car_id"] == source["source_modification_id"]
        assert state["unified_catalogue"]["payload"]["car_id"] == source["source_modification_id"]
        assert db.scalar(select(func.count()).select_from(DismantlingItem).where(
            DismantlingItem.vehicle_id==vehicle_id)) == 1
        assert db.scalar(select(func.count()).select_from(Part).where(Part.vehicle_id==vehicle_id)) == 0


def test_vin_create_rejects_wrong_make_and_does_not_persist_donor(logged, mock_catalogue):
    body=dict(manufacturer="MAN",model="XF",year=2014,
              catalogue_selection=dict(source_modification_id=430001,model_id=9300,
                manufacturer_id=144,source_snapshot_sha=SHA,confirmed=True))
    response=logged.post('/api/v1/vehicles',json=body)
    assert response.status_code == 409, response.text


def test_vin_create_rejects_changed_snapshot(logged, mock_catalogue):
    body=dict(manufacturer="DAF",model="XF",year=2014,
              catalogue_selection=dict(source_modification_id=430001,model_id=9300,
                manufacturer_id=144,source_snapshot_sha="b"*64,confirmed=True))
    response=logged.post('/api/v1/vehicles',json=body)
    assert response.status_code == 409, response.text
