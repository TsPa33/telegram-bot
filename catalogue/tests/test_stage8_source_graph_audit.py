"""Offline Stage 8 source-graph checks. Never contacts Oracle or MySQL."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage8_source_graph_audit import audit, MAX_ARTICLES


def data():
    return {
        "manufacturer_id": 120, "car_id": 107555, "coverage": "partial",
        "source_scope": "passenger_prd_article_oem",
        "categories": [{"product_id": 188, "articles": ["1:A", "2:B"]},
                       {"product_id": 288, "articles": ["3:C"]}],
        "articles": {
            "1:A": {"supplier_id": 1, "article_number": "A",
                    "oem": [{"manufacturerId": 120, "OENbr": "123"}]},
            "2:B": {"supplier_id": 2, "article_number": "B", "oem": []},
            "3:C": {"supplier_id": 3, "article_number": "C", "oem": []},
        },
    }


def test_real_source_keys_and_oem_differences_are_explicit():
    seen = []
    def snap(car_id):
        assert car_id == 107555
        return data(), "source-snapshot-checksum"
    def enrich(graph, keys):
        assert set(keys) == set(graph["articles"])
        return {"1:A": graph["articles"]["1:A"],
                "2:B": graph["articles"]["2:B"],
                "3:C": graph["articles"]["3:C"]}
    def request(path, params):
        assert "article_li" not in path and "article_links" not in path
        seen.append((path, params))
        if path.endswith("/by-article"):
            return {"fitment_verified": False, "truncated": False,
                    "items": [{"oem_number": "123"}] if params["article_number"] == "A" else []}
        assert path.endswith("/attributes")
        return {"fitment_verified": False, "vehicle_identity_only": True, "items": []}
    result = audit(snap, enrich, request)
    assert result["sampled"] == 3
    assert result["local_oe_positive"] == 1
    assert result["oracle_oe_positive"] == 1
    assert result["oracle_query_failed"] == 0
    assert result["items"][0]["common_count"] == 1
    assert result["fitment_verified"] is False
    assert result["source_coverage"] == "partial"
    assert len(seen) == 6
    assert len(result["items"]) <= MAX_ARTICLES
    assert result["modification_attributes"][1]["label"] == "XC60_T5_reference_NOT_B5"


def test_wrong_identity_and_unlinked_articles_fail_closed():
    wrong = data()
    wrong["manufacturer_id"] = 24
    with pytest.raises(ValueError, match="identity"):
        audit(lambda _: (wrong, "sha"), lambda *args: {}, lambda *args: {})
    wrong = data()
    wrong["categories"][0]["articles"].append("99:unlinked")
    with pytest.raises(ValueError, match="Missing source article"):
        audit(lambda _: (wrong, "sha"), lambda *args: {}, lambda *args: {})


def test_source_oem_claim_not_inferred_if_oracle_rejects():
    result = audit(lambda _: (data(), "sha"),
                   lambda graph, keys: {k: graph["articles"][k] for k in keys},
                   lambda path, params: {
                       "fitment_verified": True, "truncated": False, "items": []
                   } if path.endswith("/by-article") else {
                       "fitment_verified": False, "vehicle_identity_only": True, "items": []
                   })
    assert result["oracle_query_failed"] == 3
    assert result["oracle_oe_positive"] == 0
    assert result["fitment_verified"] is False
    assert all("error_class" in row for row in result["items"])
