"""Pure offline Source-First admission tests; no network or DB."""
import pytest
from app.services import source_first_pilot as policy


def snapshot(count=50, car_id=107555):
    return {
        "car_id": car_id, "source_snapshot_sha": "a" * 64,
        "categories": [
            {"product_id": pid, "kind": "review", "article_count": 1}
            for pid in range(1, count + 1)
        ],
    }


def offers(count=50, covered=40):
    return {
        pid: [{"supplier_id": 100, "article_nr": str(pid), "brand": "OEM TEST",
               "oem_numbers": [f"OE-{pid}"] if pid <= covered else []}]
        for pid in range(1, count + 1)
    }


def test_pilot_off_by_default_and_never_enabled_in_production(monkeypatch):
    monkeypatch.delenv(policy.ENABLED_VARIABLE, raising=False)
    monkeypatch.setattr(policy, "is_staging", lambda: True)
    assert policy.enabled() is False
    monkeypatch.setenv(policy.ENABLED_VARIABLE, "true")
    assert policy.enabled() is True
    monkeypatch.setattr(policy, "is_staging", lambda: False)
    assert policy.enabled() is False


def test_source_review_categories_can_be_admitted_by_complete_exact_links():
    result = policy.evaluate(snapshot(), offers())
    assert result["eligible"] is True
    assert result["reason"] == "source_first_qualified"
    assert result["source_prd_types"] == 50
    assert result["source_prd_types_with_oem"] == 40
    assert result["prd_oem_pct"] == 80
    assert result["article_oem_pct"] == 80
    assert result["vin_fitment_verified"] is False


@pytest.mark.parametrize("count", [0, 1, 16, 25, 39])
def test_small_catalogue_never_claims_qualification(count):
    result = policy.evaluate(snapshot(count), offers(count))
    assert result["eligible"] is False
    assert result["reason"] == "insufficient_prd_types"


def test_coverage_below_threshold_rejects_even_with_many_source_rows():
    result = policy.evaluate(snapshot(), offers(50, 30))
    assert result["eligible"] is False
    assert result["reason"] == "below_pilot_oem_coverage"


def test_truncated_or_missing_batch_never_looks_like_zero_coverage():
    incomplete = offers()
    incomplete.pop(2)
    result = policy.evaluate(snapshot(), incomplete)
    assert result["eligible"] is False
    assert result["reason"] == "incomplete_source_articles"
    assert result["article_oem_pct"] is None


def test_missing_supplier_name_or_oem_is_not_confirmed_reference():
    rows = offers()
    for pid in range(15, 51):
        rows[pid][0]["brand"] = ""
    result = policy.evaluate(snapshot(), rows)
    assert result["eligible"] is False
    assert result["article_keys_with_oem"] == 14


def test_invalid_article_and_duplicate_prd_fail_closed():
    rows = offers()
    rows[1][0]["supplier_id"] = None
    assert policy.evaluate(snapshot(), rows)["reason"] == "invalid_article"
    item = snapshot()
    item["categories"][1]["product_id"] = 1
    assert policy.evaluate(item, offers())["reason"] == "duplicate_prd"


def test_invalid_article_count_or_identity_is_rejected():
    s = snapshot()
    s["categories"][0]["article_count"] = "1"
    assert policy.evaluate(s, offers())["reason"] == "invalid_source_type"
    s = snapshot()
    s["source_snapshot_sha"] = "none"
    assert policy.evaluate(s, offers())["reason"] == "invalid_snapshot"


def test_zero_article_types_lower_prd_coverage_without_faking_coverage():
    s = snapshot()
    for p in s["categories"][40:]:
        p["article_count"] = 0
    r = offers()
    for key in range(41, 51):
        r.pop(key)
    result = policy.evaluate(s, r)
    assert result["eligible"] is True
    assert result["source_prd_types"] == 50
    assert result["source_prd_types_with_oem"] == 40


def test_equipment_is_never_added_as_a_dismantling_part():
    s = snapshot()
    s["categories"].append({"product_id": 99, "kind": "equipment", "article_count": 2})
    r = policy.evaluate(s, offers())
    assert r["eligible"] is True
    assert r["source_prd_types"] == 50
