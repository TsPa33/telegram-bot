"""Stage 12 regression: source-only model/variant dropdown, zero invented stock."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Vehicle,DismantlingItem,Part
from app.services import vin_source_directory as directory
from app.services import unified_catalogue as catalogue

class Oracle:
    def get(self,path,params=None):
        params=params or {}
        assert path.startswith("global:oracle/vehicles/"),path
        endpoint=path.split("/")[-1]
        kind=params.get("kind")
        if endpoint=="manufacturers":
            items=[dict(id=88,name="DAF")] if kind=="commercial" and params["name"].casefold()=="daf" else []
        elif endpoint=="models":
            items=[dict(id=901,name="XF",construction_interval="2005 - 2013")] if (
                params["manufacturer_id"]==88 and kind=="commercial"
                and params["after"]<901) else []
        elif endpoint=="modifications":
            items=[dict(id=14200,model_id=901,name="XF105 460",
                        construction_interval="2006 - 2013")] if (
                params["model_id"]==901 and kind=="commercial"
                and params["after"]<14200) else []
        else:
            raise AssertionError(path)
        return dict(source="oracle",kind=kind,items=items,
                    next_after=None,vehicle_identity_only=True,
                    truncated=False,fitment_verified=False)

@pytest.fixture
def oracle(monkeypatch):
    provider=Oracle()
    monkeypatch.setattr(catalogue.CatalogueAdapter,"get",
                        lambda self,path,params=None:provider.get(path,params))
    return provider


def test_daf_source_browser_has_models_and_modifications(logged,oracle):
    a=logged.get("/api/v1/vehicles/vin/source-manufacturers?manufacturer=Daf")
    assert a.status_code==200,a.text
    assert a.json()["items"]==[dict(manufacturer_id=88,manufacturer="DAF",kind="commercial")]
    b=logged.get("/api/v1/vehicles/vin/source-models?manufacturer_id=88&kind=commercial")
    assert b.status_code==200,b.text
    assert b.json()["items"][0]["name"]=="XF"
    c=logged.get("/api/v1/vehicles/vin/source-modifications?model_id=901&kind=commercial")
    assert c.status_code==200,c.text
    assert c.json()["items"][0]["name"]=="XF105 460"
    assert c.json()["vin_fitment_verified"] is False


def test_source_selection_creates_donor_but_no_catalogue_or_stock(logged,oracle):
    body=dict(manufacturer="DAF",model="XF",year=2012,
              source_identity=dict(kind="commercial",manufacturer_id=88,
                                   model_id=901,source_modification_id=14200,confirmed=True))
    response=logged.post("/api/v1/vehicles",json=body)
    assert response.status_code==201,response.text
    vid=response.json()["id"]
    with Session(engine()) as db:
        v=db.get(Vehicle,vid)
        selected=v.dismantling_v3["oracle_vehicle_identity"]
        assert selected["source_modification_id"]==14200
        assert selected["confirmation"]=="user_selected_identity_only"
        assert selected["vin_fitment_verified"] is False
        assert selected["parts_graph_verified"] is False
        assert "global_selection" not in v.dismantling_v3
        assert "unified_catalogue" not in v.dismantling_v3
        assert db.scalar(select(func.count()).select_from(Part).where(Part.vehicle_id==vid))==0
        assert db.scalar(select(func.count()).select_from(DismantlingItem).where(
            DismantlingItem.vehicle_id==vid))==0


def test_oracle_model_cannot_be_used_with_different_vehicle_model(logged,oracle):
    body=dict(manufacturer="DAF",model="FT",source_identity=dict(
        kind="commercial",manufacturer_id=88,model_id=901,
        source_modification_id=14200,confirmed=True))
    response=logged.post("/api/v1/vehicles",json=body)
    assert response.status_code==409,response.text


def test_oracle_bad_make_or_bad_modification_not_saved(logged,oracle):
    for values in [dict(manufacturer="MAN",model="XF",manufacturer_id=88,source_modification_id=14200),
                   dict(manufacturer="DAF",model="XF",manufacturer_id=88,source_modification_id=14201),
                   dict(manufacturer="DAF",model="XF",manufacturer_id=89,source_modification_id=14200)]:
        manufacturer=values.pop("manufacturer")
        model=values.pop("model")
        body=dict(manufacturer=manufacturer,model=model,source_identity=dict(
            kind="commercial",manufacturer_id=values["manufacturer_id"],
            model_id=901,source_modification_id=values["source_modification_id"],confirmed=True))
        response=logged.post("/api/v1/vehicles",json=body)
        assert response.status_code==409,response.text


def test_cannot_mix_pinned_and_source_only_modifications(logged,oracle):
    response=logged.post("/api/v1/vehicles",json=dict(manufacturer="DAF",model="XF",
        source_identity=dict(kind="commercial",manufacturer_id=88,model_id=901,
                             source_modification_id=14200,confirmed=True),
        catalogue_selection=dict(source_modification_id=14200,model_id=901,
                                 manufacturer_id=88,source_snapshot_sha="a"*64,confirmed=True)))
    assert response.status_code==422,response.text


def test_maker_validation_rejects_unverified_identity(oracle):
    from types import SimpleNamespace
    selection=SimpleNamespace(kind="commercial",manufacturer_id=88,model_id=901,
                              source_modification_id=14200)
    item=directory.confirm_identity(selection,manufacturer="DAF",model="XF",adapter=oracle)
    assert item["modification"]=="XF105 460"
    assert item["parts_graph_verified"] is False
