"""Regression coverage for exact source graph / physical placement separation."""
from copy import deepcopy

import pytest

from app.services.catalogue_format import digest
from app.services.master_parts_reconciliation import reconcile, linked_offers, physical_key


def entry(key, pids, hint="single"):
    return {"key": key, "name_uk": key, "category_path": ["body", "parts"],
            "prd_ids": pids, "condition": "all", "placement_hint": hint}


def saved():
    graph = {"items": [[2, "A1", "Supplier", ["OE-1"]],
                       [2, "A2", "Supplier", ["OE-2"]]],
             "product_links": {"10": [0], "11": [1]}}
    payload = {"kind": "passenger", "manufacturer_id": 5, "model_id": 7534,
               "car_id": 119996, "source_snapshot_sha": "a" * 64,
               "article_graph_sha": digest(graph), "categories": [
                   {"product_id": 10, "kind": "part", "article_count": 1,
                    "source_fitment_linked": True},
                   {"product_id": 11, "kind": "part", "article_count": 1,
                    "source_fitment_linked": True}]}
    return {"payload": payload, "sha256": digest(payload), "article_graph": graph}


def repin(s):
    s["payload"]["article_graph_sha"] = digest(s["article_graph"])
    s["sha256"] = digest(s["payload"])
    return s


def profile():
    return {"kind": "passenger", "body": "suv",
            "side_doors": ["FL", "FR", "RL", "RR"], "rear_closure": "liftgate"}


def test_source_rows_preserved_and_door_ids_distinct():
    s = saved()
    before = deepcopy(s)
    seed = [entry("door", [10], "doors"), entry("dashboard", [11]), entry("windscreen", [])]
    r = reconcile(s, profile(), seed=seed)
    assert s == before
    assert r["source_rows_retained"] == 2
    assert r["physical_candidate_count"] == 6
    doors = [x for x in r["positions"] if x["master_key"] == "door"]
    assert len(doors) == len({x["physical_key"] for x in doors}) == 4
    assert all(x["state"] == "reconcile" and x["oem"] is None
               and not x["source_article_candidates"] for x in doors)
    dash = next(x for x in r["positions"] if x["master_key"] == "dashboard")
    assert dash["source_article_candidates"][0]["oem_numbers"] == ["OE-2"]
    assert dash["oem"] is None
    assert r["automatically_assigned_physical_oem"] == 0
    assert r["gap_candidate_count"] == 1
    assert not r["persisted"] and not r["stock_changed"]


def test_existing_generic_and_unknown_rows_block_duplicate_supplements():
    r = reconcile(saved(), profile(), seed=[entry("door", [10], "doors"),
                  entry("windscreen", [])], existing_rows=[{"row_id": "old", "protected": True}])
    assert r["gap_candidate_count"] == 0
    assert r["reconciliation_count"] == 5


def test_idempotent_keys_and_no_fabricated_unknown_door_positions():
    assert physical_key("door", "door:FL") == physical_key("door", "door:FL")
    assert physical_key("door", "door:FL") != physical_key("door", "door:FR")
    r = reconcile(saved(), {"kind": "passenger"}, seed=[entry("door", [10], "doors")])
    assert not r["positions"]
    assert r["review"][0]["master_key"] == "door"


@pytest.mark.parametrize("mutate", [
    lambda s: s["article_graph"]["product_links"].update({"10": [99]}),
    lambda s: s["article_graph"]["product_links"].update({"10": []}),
    lambda s: s["article_graph"]["product_links"].update({"999": [0]}),
    lambda s: s["article_graph"]["items"].append([2, "A1", "Supplier", ["OE-3"]]),
    lambda s: s["article_graph"]["items"][0].__setitem__(3, [""]),
])
def test_invalid_graph_rejected_even_if_repinned(mutate):
    s = saved()
    mutate(s)
    with pytest.raises(ValueError):
        linked_offers(repin(s))


def test_tampered_graph_and_snapshot_rejected():
    s = saved()
    s["article_graph"]["items"][0][3] = ["different"]
    with pytest.raises(ValueError):
        reconcile(s, profile(), seed=[])
    s = saved()
    s["payload"]["car_id"] = 99
    with pytest.raises(ValueError):
        reconcile(s, profile(), seed=[])


def test_missing_compact_graph_is_not_oem_proof():
    s = saved()
    s.pop("article_graph")
    r = reconcile(s, profile(), seed=[entry("dashboard", [11])])
    assert r["source_types_with_oem"] == 0
    assert not r["positions"][0]["source_article_candidates"]


def test_reference_profile_requires_exact_namespace_year_and_no_conflict():
    from app.services.master_parts_reconciliation import pinned_identity, reference_profile
    identity = pinned_identity(saved())
    base = {"kind": "passenger", "fuel": "petrol", "counts": {"cylinders": 4}}
    result = reference_profile(identity, 2014, base)
    assert result["profile"]["side_doors"] == ["FL", "FR", "RL", "RR"]
    assert result["profile"]["counts"]["cylinders"] == 4
    assert result["physical_fitment_verified"] is False
    assert reference_profile(identity, 2013, base) is None
    assert reference_profile({**identity, "car_id": 999}, 2014, base) is None
    assert reference_profile(identity, 2014, {**base, "fuel": "diesel"}) is None
    assert reference_profile(identity, 2014, {**base, "counts": {"cylinders": 6}}) is None
    assert base == {"kind": "passenger", "fuel": "petrol", "counts": {"cylinders": 4}}
