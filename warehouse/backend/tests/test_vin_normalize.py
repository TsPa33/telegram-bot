from app.services.vin_normalize import ukrainian, merge_verified, normalize

def test_ukrainian_descriptors():
    assert ukrainian("drive_type", "Front-wheel drive") == "Передній (FWD)"
    assert ukrainian("drive_type", "4WD") == "Повний (4WD)"
    assert ukrainian("body_class", "Wagon") == "Універсал"
    assert ukrainian("body_class", "Pickup") == "Пікап"
    assert ukrainian("transmission", "6-Speed Automatic") == "6-ступенева автоматична"
    assert ukrainian("transmission", "6MT") == "6-ступенева механічна"
    assert ukrainian("fuel_type", "Diesel") == "Дизель"

def test_never_replace_conflicting_vin_facts():
    result, conflicts=merge_verified(
        {"manufacturer":"Ford","model":"F-150","engine":"5.0L V6","year":2013,"transmission":""},
        {"model":"F-150","engine":"3.5L V6","transmission":"6-Speed Automatic","year":2013})
    assert result["engine"]=="5.0L V6"
    assert result["transmission"]=="6-ступенева автоматична"
    assert conflicts["engine"]["secondary"]=="3.5L V6"

def test_technical_codes_preserved():
    assert normalize({"engine":"D4204T14","trim":"Inscription"})=={"engine":"D4204T14","trim":"Inscription"}

def test_conflicting_engine_volume_is_flagged():
    from app.services.vin_normalize import validate_consistency
    result=validate_consistency({"engine":"5.0L V6 DOHC","engine_displacement_l":3.5})
    assert "engine_displacement_l" in result
    assert "5" in result["engine_displacement_l"]
    assert "3.5" in result["engine_displacement_l"]

def test_matching_engine_volume_is_not_flagged():
    from app.services.vin_normalize import validate_consistency
    assert validate_consistency({"engine":"3.5L V6","engine_displacement_l":3.5})=={}
    assert validate_consistency({"engine":"D4204T14","engine_displacement_l":2.0})=={}
