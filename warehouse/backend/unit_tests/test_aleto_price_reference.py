from decimal import Decimal
from app.services.aleto_price_reference import summarize_aleto


def offer(i, amount, *, currency="UAH", condition="used", exact=False, **overrides):
    return {"exact": exact, "entry": dict(source="aleto", article=str(i), amount=str(amount),
        currency=currency, condition=condition, url="https://aleto.ua/ua/detail/test/",
        observed_at="2026-11-26T12:00:00+00:00", **overrides)}


def test_average_and_range_from_similar_offers():
    g = summarize_aleto([offer(1,1000), offer(2,1500), offer(3,2000)])[0]
    assert (Decimal(g["average"]), Decimal(g["minimum"]), Decimal(g["maximum"])) == (1500,1000,2000)
    assert g["offer_count"] == 3 and g["match"] == "similar"


def test_full_sample_and_no_currency_condition_mixing():
    rows = [offer(i, i+1) for i in range(20)]
    rows += [offer(1,2), offer(30,9000,currency="USD"), offer(31,8000,condition="new"), offer(32,7000,exact=True)]
    groups = summarize_aleto(rows)
    g = next(x for x in groups if x["currency"]=="UAH" and x["condition"]=="used" and x["match"]=="similar")
    assert g["offer_count"] == 20 and len(g["examples"]) == 10
    assert Decimal(g["average"]) == Decimal("10.55")
    assert all(x["average"] is None for x in groups if x is not g)


def test_invalid_conflicting_and_truncated_results():
    rows = [offer(1,1000), offer(2,1500), offer(3,2000)]
    assert summarize_aleto(rows,truncated=True) == []
    rows[0]["conflict"] = True
    rows[1]["entry"]["url"] = "https://aleto.ua.evil.test/x"
    rows[2]["entry"]["status"] = "historical_not_recommendation"
    assert summarize_aleto(rows) == []
