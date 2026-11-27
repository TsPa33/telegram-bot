"""Master positions may enter managed v3 only as potential physical items."""
from types import SimpleNamespace

from app.services import master_parts_managed as managed
from app.services.master_parts_reconciliation import reported_topology, physical_key


def test_staging_flag_is_explicit_and_not_production(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_MASTER_PARTS_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_ENV", "production")
    assert not managed.enabled()
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    assert managed.enabled()
    monkeypatch.delenv("WAREHOUSE_MASTER_PARTS_ENABLED")
    assert not managed.enabled()


def item(key, place, state="supplement_candidate", sources=()):
    return dict(master_key=key, placement=place, state=state,
                source_ids=list(sources), name_uk=key, category_path=["Кузов","Двері"])


def test_unique_physical_positions_and_no_source_row_replacement():
    identity = {"kind":"passenger","car_id":1,"model_id":2,"manufacturer_id":3,"snapshot_sha":"a"*64}
    report = dict(identity=identity, positions=[
        item("door", "door:FL"), item("door", "door:FR"),
        item("door", "door:RL"), item("door", "door:RR"),
        item("brake_disc", "axle:1:L", "reconcile", [82]),
        item("glass", "unit:1", "supplement_candidate", [5]),
    ])
    rows = managed.candidate_rows(report, basis="basis")
    assert len(rows) == 4
    assert len({r["placement"]["id"] for r in rows}) == 4
    assert {r["placement"]["side"] for r in rows} == {"left","right"}
    assert {r["placement"]["position"] for r in rows} == {"front","rear"}
    assert all(not r["variants"] and not r["source_confirmed"] for r in rows)
    assert rows == managed.candidate_rows(report, basis="basis")
    ref = rows[0]["source_refs"][0]
    assert ref["key"] == physical_key("door", "door:FL")
    assert ref["identity"] == identity


def test_reference_candidates_remain_unverified():
    report = dict(identity={"kind":"passenger"},positions=[],reference_projection={
        "reference_id":"r1", "positions":[item("mirror","L")]})
    row, = managed.candidate_rows(report,basis="b")
    assert row["source_refs"][0]["reference_id"] == "r1"
    assert row["applicability"]["missing_or_unverified"] == ["physical_inspection"]
    assert not row["source_confirmed"]


def test_reported_doors_are_brand_independent_and_not_inferred_from_body_alone():
    base = {"kind":"passenger"}
    d = {"trust":"server_vin_report_with_operator_review",
         "characteristics":{"body_class":"SUV","doors":5,"engine_cylinders":4}}
    result = reported_topology(base,d)
    assert result["side_doors"] == ["FL","FR","RL","RR"]
    assert result["counts"]["cylinders"] == 4
    assert base == {"kind":"passenger"}
    d["characteristics"]["body_class"]="coupe"
    d["characteristics"]["doors"]=2
    assert reported_topology(base,d)["side_doors"] == ["FL","FR"]
    del d["characteristics"]["doors"]
    assert "side_doors" not in reported_topology(base,d)
    truck = reported_topology({"kind":"heavy_truck"}, d)
    assert "side_doors" not in truck and "body" not in truck
    assert truck["counts"]["cylinders"] == 4
    d["trust"]="user_confirmed_reported_not_factory_verified"
    assert reported_topology(base,d) == base


def test_receipt_quantity_and_stale_source_fail_closed():
    r = SimpleNamespace(plan_v3={"snapshot":{"source":[{"kind":managed.KIND}]}})
    assert not managed.receipt_allowed(None,r,1)
    assert not managed.receipt_allowed(None,r,2)
    assert managed.receipt_allowed(None,SimpleNamespace(plan_v3={}),1)


def test_auto_oem_does_not_infer_master_fitment():
    from app.services.auto_oem import matches
    r = SimpleNamespace(plan_v3={"snapshot":{"source":[{"kind":managed.KIND}]}},
                        name="Door")
    assert matches(r,{}) is None


def test_reference_conflict_prevents_using_wrong_powertrain_or_gearbox():
    assert managed.profile_conflicts({"powertrain":"ICE"}, {"powertrain":"BEV"})
    assert managed.profile_conflicts({"transmission":"automatic"}, {"transmission":"manual"})
    assert not managed.profile_conflicts({"body":"hatch"}, {"body_type":"hatchback"})
    assert not managed.profile_conflicts({"transmission":"automatic"}, {})


def test_intake_is_disabled_without_feature_and_does_not_touch_db(monkeypatch):
    monkeypatch.setattr(managed, "enabled", lambda: False)
    assert managed.auto_supplement_new_donor(None,None,None) is None
