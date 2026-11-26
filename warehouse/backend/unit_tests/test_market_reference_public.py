from app.services.market_reference_public import public_reference


def test_public_response_allowlist_strips_provenance():
    e=dict(amount="1000",currency="UAH",observed_at="2026-11-26",source="secret-provider",url="https://vendor.example",article="private-123",oem="other",differences=["internal note"])
    raw=dict(status="completed",fresh_data_fetched=False,source_reason="private",external_url=e["url"],guidance=dict(aleto_reference=[dict(currency="UAH",condition="used",match="similar",offer_count=3,minimum="1000",maximum="2000",average="1500",observed_at=e["observed_at"],examples=[e],source="secret-provider")]),offers=[dict(e,status="historical_not_recommendation")])
    result=public_reference(raw)
    assert result["references"][0]["average"]=="1500"
    assert result["references"][0]["examples"]==[dict(amount="1000",currency="UAH",observed_at="2026-11-26")]
    assert result["historical"]==result["references"][0]["examples"]
    assert all(v not in str(result) for v in ("secret-provider","vendor.example","private-123","internal note","aleto"))
