"""Focused Oracle OEM enrichment regressions. Offline: no real API or MySQL."""
import httpx
import pytest

from app.services import auto_oem
from app.services.unified_catalogue import CatalogueAdapter, CatalogueUnavailable


def enable_oracle(monkeypatch):
    monkeypatch.setattr(auto_oem, "is_staging", lambda: True)
    monkeypatch.setenv("WAREHOUSE_ORACLE_OEM_ENABLED", "true")


def test_catalogue_adapter_oracle_contract_and_credentials(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_CATALOGUE_URL", "https://catalogue.example.test")
    monkeypatch.setenv("WAREHOUSE_CATALOGUE_HOST", "catalogue.example.test")
    monkeypatch.setenv("WAREHOUSE_CATALOGUE_KEY", "private-warehouse-token")

    def respond(request):
        assert request.url.path == "/api/v1/oracle/oem/by-article"
        assert request.headers["X-Catalogue-Key"] == "private-warehouse-token"
        assert request.url.params["supplier_id"] == "1"
        assert request.url.params["article_number"] == "20064"
        assert request.url.params["manufacturer_id"] == "120"
        assert request.url.params["limit"] == "50"
        return httpx.Response(200, json={
            "source": "oracle", "supplier_id": 1, "article_number": "20064",
            "manufacturer_id": 120, "items": [
                {"oem_number": "31256232"}, {"oem_number": "272440"},
                {"oem_number": "31256231"}, {"oem_number": "272440"}
            ], "fitment_verified": False, "truncated": False,
        })

    adapter = CatalogueAdapter(transport=httpx.MockTransport(respond))
    assert adapter.oracle_oem_by_article(1, "20064", 120) == [
        "272440", "31256231", "31256232"
    ]


@pytest.mark.parametrize("bad", [
    {"manufacturer_id": 999},
    {"source": "untrusted"},
    {"fitment_verified": True},
    {"truncated": True},
    {"items": [{"oem_number": ""}]},
])
def test_oracle_response_fail_closed(monkeypatch, bad):
    monkeypatch.setenv("WAREHOUSE_CATALOGUE_URL", "https://catalogue.example.test")
    monkeypatch.setenv("WAREHOUSE_CATALOGUE_HOST", "catalogue.example.test")
    monkeypatch.setenv("WAREHOUSE_CATALOGUE_KEY", "test-token")
    data = dict(source="oracle", supplier_id=1, article_number="20064",
                manufacturer_id=120, items=[{"oem_number": "272440"}],
                fitment_verified=False, truncated=False)
    data.update(bad)
    adapter = CatalogueAdapter(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=data)
    ))
    with pytest.raises(CatalogueUnavailable):
        adapter.oracle_oem_by_article(1, "20064", 120)


def test_offline_oracle_offers_are_source_linked_and_bounded(monkeypatch):
    enable_oracle(monkeypatch)
    class Adapter:
        def __init__(self):
            self.calls = []
        def oracle_oem_by_article(self, sid, article, mid):
            self.calls.append((sid, article, mid))
            return ["272440"] if article == "20064" else []

    provider = Adapter()
    cache = auto_oem.SourceCache(provider)
    payload = {"manufacturer_id": 120}
    data = {}
    for pid in range(40):
        data[pid] = [dict(supplier_id=1, article_nr=str(20064+pid),
                          brand="BOSCH", oem_numbers=[], oem_sources={},
                          vin_verified=False)]
    enriched = cache.enrich_oracle_offers(payload, data)
    assert len(provider.calls) <= auto_oem.ORACLE_LOOKUP_LIMIT
    assert enriched[0][0]["oem_numbers"] == ["272440"]
    assert enriched[0][0]["oem_sources"]["272440"] == "oracle_gateway_cross_reference"
    assert enriched[0][0]["vin_verified"] is False
    assert enriched[39][0]["oem_numbers"] == []

    cache.enrich_oracle_offers(payload, {0: [dict(
        supplier_id=1, article_nr="20064", brand="BOSCH",
        oem_numbers=[], oem_sources={},
    )]})
    assert provider.calls.count((1, "20064", 120)) == 1


def test_exact_supplier_article_falls_back_to_oracle_without_fitment(monkeypatch):
    enable_oracle(monkeypatch)
    class Adapter:
        def exact_oem(self, *args):
            raise CatalogueUnavailable("old catalogue missing")
        def oracle_oem_by_article(self, sid, article, mid):
            assert (sid, article, mid) == (1, "20064", 120)
            return ["31256232", "272440", "31256231"]
    cache = auto_oem.SourceCache(Adapter())
    result = cache.exact_lookup("Volvo", "BOSCH", "20064", 1, manufacturer_id=120)
    assert result["oem_numbers"] == ["272440", "31256231", "31256232"]
    assert result["oem_source"] == "oracle_gateway_cross_reference"
    assert result["manufacturer_id"] == 120
    assert cache.exact_lookup("Volvo", "BOSCH", "20064", 1, manufacturer_id=120) == result


def test_oracle_fail_closed_outside_staging(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ORACLE_OEM_ENABLED", "true")
    monkeypatch.setattr(auto_oem, "is_staging", lambda: False)
    class ForbiddenAdapter:
        def oracle_oem_by_article(self, *args):
            raise AssertionError("must never query Oracle")
    assert auto_oem.SourceCache(ForbiddenAdapter()).oracle_numbers(120, 1, "20064") is None


def test_oracle_requires_source_manufacturer_and_supplier(monkeypatch):
    enable_oracle(monkeypatch)
    class ForbiddenAdapter:
        def exact_oem(self, *args):
            raise CatalogueUnavailable("not available")
        def oracle_oem_by_article(self, *args):
            raise AssertionError("missing verified identity")
    cache = auto_oem.SourceCache(ForbiddenAdapter())
    assert cache.exact_lookup("Volvo", "BOSCH", "20064", None, manufacturer_id=120) is None
    assert cache.oracle_numbers(None, 1, "20064") is None
    assert cache.oracle_numbers(120, None, "20064") is None
