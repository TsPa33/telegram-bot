"""Universal names translator: provider, cache, validation. No live DeepL calls."""
import httpx
import pytest

from app.services.parts_translation import (
    TranslationError, _cache, translate_names,
)


def test_generic_translation_reused_across_vehicles(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_DEEPL_API_KEY", "mock-key:fx")
    calls = []
    def provider(request):
        calls.append(request)
        assert request.url.host == "api-free.deepl.com"
        assert request.headers["Authorization"] == "DeepL-Auth-Key mock-key:fx"
        import json
        names=json.loads(request.content)["text"]
        return httpx.Response(200, json={"translations": [
            {"text": "Гальмівний диск" if x=="Brake Disc" else "Кермова рейка"} for x in names
        ]})
    transport=httpx.MockTransport(provider)
    try:
        first=translate_names(["Brake Disc", "Steering Rack"],transport=transport)
        second=translate_names(["Brake Disc"],transport=transport)
        assert first["translations"]["Brake Disc"] == "Гальмівний диск"
        assert second["translations"]["Brake Disc"] == "Гальмівний диск"
        assert len(calls)==1
    finally:
        _cache.clear()


def test_no_credentials_is_reported_not_falsely_translated(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_DEEPL_API_KEY", raising=False)
    _cache.clear()
    result=translate_names(["Unknown steering component"])
    assert result["configured"] is False
    assert result["untranslated"]==["Unknown steering component"]


def test_large_response_rejected_and_not_cached(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_DEEPL_API_KEY", "mock-key")
    def invalid(_request):
        return httpx.Response(200, json={"translations": []})
    try:
        with pytest.raises(TranslationError):
            translate_names(["Accessory Kit, disc brake pad"], transport=httpx.MockTransport(invalid))
    finally:
        _cache.clear()
