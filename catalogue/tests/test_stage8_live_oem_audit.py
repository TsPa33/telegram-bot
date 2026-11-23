"""Stage 8 source-only acceptance; no live Oracle and no paid API usage."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage8_live_oem_audit import _checked, audit


def test_audit_is_bounded_and_stays_in_source_tables():
    requests = []

    def source(path, params):
        requests.append((path, params))
        assert "article_li" not in path and "article_links" not in path
        assert 1 <= params.get("limit", 20) <= 50
        if path.endswith("/manufacturers"):
            name = params["name"]
            return {"truncated": False, "fitment_verified": False,
                    "vehicle_identity_only": True,
                    "items": [{"id": 120 if name == "Volvo" else 88, "name": name}]}
        if path.endswith("/models"):
            rows = ([{"id": 13084, "name": "XC90 II"},
                     {"id": 37773, "name": "XC60 II"}] if params["kind"] == "passenger"
                    else [{"id": 901, "name": "95 XF"}])
            return {"truncated": False, "fitment_verified": False,
                    "vehicle_identity_only": True, "items": rows}
        if path.endswith("/modifications"):
            model_id = params["model_id"]
            return {"truncated": False, "fitment_verified": False,
                    "vehicle_identity_only": True, "items": [
                        {"id": 107555 if model_id == 13084 else 8888,
                         "model_id": model_id, "name": "Variant"}
                    ]}
        if path.endswith("/attributes"):
            return {"truncated": False, "fitment_verified": False,
                    "vehicle_identity_only": True, "items": [
                        {"attribute_type": "EngineCode", "display_value": "B4204T27"}
                    ]}
        if path.endswith("/prd"):
            return {"truncated": False, "fitment_verified": False,
                    "items": [{"node_id": 99, "product_id": 188, "supplier_id": 112}]}
        if path.endswith("/by-article"):
            return {"truncated": False, "fitment_verified": False,
                    "items": [{"oem_number": "OE-TEST"}]}
        raise AssertionError(path)

    result = audit(source)
    assert result["read_only"] is True and result["fitment_verified"] is False
    assert result["manufacturers"]["DAF"]["manufacturer_ids"] == [88]
    assert result["candidate_models"]["DAF"][0]["id"] == 901
    assert result["modifications"]["DAF_901"]["items"][0]["model_id"] == 901
    assert result["oem_reference_samples"][0]["oem_numbers"] == ["OE-TEST"]
    assert all(c["status"] == "ok" for c in result["checks"])
    assert len(requests) < 30


@pytest.mark.parametrize("invalid", [
    {"truncated": 0, "fitment_verified": False, "vehicle_identity_only": True, "items": []},
    {"truncated": False, "fitment_verified": True, "vehicle_identity_only": True, "items": []},
    {"truncated": False, "fitment_verified": False, "items": []},
    {"truncated": False, "fitment_verified": False, "vehicle_identity_only": True, "items": ["wrong"]},
])
def test_vehicle_source_rejects_untrusted_contract(invalid):
    with pytest.raises(ValueError):
        _checked(invalid, vehicle=True)


def test_gateway_failures_reported_without_secret_or_false_fitment():
    def reject(path, params):
        raise RuntimeError("sensitive upstream detail")
    result = audit(reject)
    assert all(c["status"] == "failed" for c in result["checks"])
    assert "sensitive" not in str(result)
    assert result["fitment_verified"] is False
    assert result["excluded_tables"] == ["article_li", "article_links"]
