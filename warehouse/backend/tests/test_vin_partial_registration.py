"""Partial VIN donor registration must not require invented year or passenger-car engine size."""
from app.services.vin_normalize import drive_code

VIN_DAF = "XLRTE47MS0E774889"


def test_vin_donor_with_unknown_year_and_large_engine(logged):
    created=logged.post("/api/v1/vehicles",json={
        "manufacturer":"DAF","model":"FT","year":None,
        "vin":VIN_DAF,"engine_displacement_l":12.9,
        "fuel_type":"Дизель","drive_type":None,
        "vin_details":{"source":"manual","characteristics":{"year":None,"engine_displacement_l":"12.9"}}
    })
    assert created.status_code==201,created.text
    data=created.json()
    assert data["year"] is None
    assert float(data["engine_displacement_l"])==12.9
    assert data["vin"]==VIN_DAF
    retrieved=logged.get("/api/v1/vehicles/"+data["id"])
    assert retrieved.status_code==200
    assert retrieved.json()["year"] is None
    assert logged.post("/api/v1/vehicles",json={
        "manufacturer":"DAF","model":"FT","year":None,"vin":VIN_DAF
    }).status_code==409


def test_manual_donor_without_year_does_not_claim_model_year(logged):
    response=logged.post("/api/v1/vehicles",json={
        "manufacturer":"Невідома марка","model":"Потребує уточнення"
    })
    assert response.status_code==201,response.text
    assert response.json()["year"] is None


def test_year_range_and_large_engine_validation(logged):
    base={"manufacturer":"Example","model":"Test"}
    assert logged.post("/api/v1/vehicles",json={**base,"year":1700}).status_code==422
    assert logged.post("/api/v1/vehicles",json={**base,"engine_displacement_l":100.0}).status_code==422
    assert logged.post("/api/v1/vehicles",json={**base,"engine_displacement_l":12.9}).status_code==201


def test_drive_code_does_not_guess_drive_from_truck_model():
    assert drive_code("FT")=="" 
    assert drive_code("Повний привід (AWD)")=="AWD"
