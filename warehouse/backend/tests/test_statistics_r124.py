"""R12.4: never confuse a zero price with an absent price."""
from test_warehouse import op

def test_dashboard_counts_explicit_prices_separately_from_missing_prices(logged,vehicle,part):
    assert op(logged,part,"receipt",2).status_code==200
    other=logged.post("/api/v1/parts",json={"name":"Unpriced part","vehicle_id":vehicle["id"]})
    assert other.status_code==201,other.text
    assert op(logged,other.json(),"receipt",1).status_code==200
    zero=logged.post("/api/v1/parts",json={"name":"Explicit zero","vehicle_id":vehicle["id"],"selling_price":"0.00"})
    assert zero.status_code==201,zero.text
    assert op(logged,zero.json(),"receipt",1).status_code==200
    response=logged.get("/api/v1/dashboard")
    assert response.status_code==200,response.text
    values=[r for r in response.json()["vehicle_valuation_by_currency"] if r["id"]==vehicle["id"] and r["currency"]=="UAH"]
    assert len(values)==1
    assert values[0]["priced_positions"]==2
    assert values[0]["unpriced_positions"]==1
    assert float(values[0]["value"])==100
