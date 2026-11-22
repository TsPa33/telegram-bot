"""Fail-closed VIN-to-source-identity tests, using real XC60/90 source labels.

No network, provider credits, MySQL, fixture VIN database or OEM writes.
"""
from types import SimpleNamespace

from app.services.auto_oem import SourceCache


def vehicle(**overrides):
    base=dict(manufacturer="Volvo", model="XC60", generation="",
              engine_code="", year=2022, fuel_type="hybrid",
              drive_type="AWD", engine_variant="B5",
              engine_displacement_l=2.0)
    base.update(overrides)
    return SimpleNamespace(**base)


def candidate(cid, label, *, maker="Volvo", model="XC60 II (246)", mid=37773,
              fuel="petrol", drive="AWD", engine=""):
    return dict(manufacturer=maker,model=model,source_modification_id=cid,
        model_id=mid,manufacturer_id=120,snapshot_sha="a"*64,
        modification=dict(description=label,constructioninterval="03.2017 -"),
        specifications=[
          dict(attributetype="ConstructionInterval",displayvalue="03.2017 -"),
          dict(attributetype="FuelType",displayvalue=fuel),
          dict(attributetype="DriveType",displayvalue=drive),
          dict(attributetype="EngineCode",displayvalue=engine),
          dict(attributetype="Capacity",displayvalue="2.0 l")])


def test_xc60_2022_b5_mhev_is_not_automatically_mislabeled_as_t5():
    cache=SourceCache()
    cache.directory=[
        candidate(126478,"2.0 D4 AWD",fuel="diesel"),
        candidate(126479,"2.0 D5 AWD",fuel="diesel"),
        candidate(126480,"2.0 T5 AWD"),
        candidate(126481,"2.0 T6 AWD"),
        candidate(126482,"2.0 T8 Hybrid AWD",fuel="hybrid"),
        candidate(128114,"2.0 T5",drive="FWD")
    ]
    # 'B5' is not the same drive-train as T5 or T8.
    assert cache.resolve_directory(vehicle()) is None


def test_xc60_missing_engine_version_does_not_choose_first_of_two():
    cache=SourceCache()
    cache.directory=[candidate(126480,"2.0 T5 AWD"),
                     candidate(126481,"2.0 T6 AWD")]
    assert cache.resolve_directory(vehicle(engine_variant="",fuel_type="petrol")) is None


def test_unambiguous_xc90_exact_engine_can_resolve_to_source_id():
    cache=SourceCache()
    cache.directory=[candidate(107555,"2.0 T6 AWD",model="XC90 II",
        mid=13084,engine="B4204T27")]
    v=vehicle(model="XC90",year=2016,engine_code="B4204T27",
        engine_variant="T6",fuel_type="petrol")
    # XC90 source starts September 2014.
    cache.directory[0]["modification"]["constructioninterval"]="09.2014 -"
    cache.directory[0]["specifications"][0]["displayvalue"]="09.2014 -"
    assert cache.resolve_directory(v)==(107555,13084,120,"a"*64,True)


def test_daf_without_imported_commercial_candidate_is_not_guessed():
    cache=SourceCache()
    cache.directory=[]
    v=vehicle(manufacturer="DAF",model="XF",generation="",
              year=2007,engine_code="",fuel_type="diesel",
              drive_type="RWD",engine_variant="",engine_displacement_l=12.9)
    assert cache.resolve_directory(v) is None


def test_saved_legacy_first_match_is_not_reused_for_oem():
    from app.services.auto_oem import automatic_identity
    donor=SimpleNamespace(dismantling_v3={
        "automatic_catalogue_identity": {
            "confirmation": "auto_assumed",
            "car_id":126480,
            "model_id":37773,
            "manufacturer_id":120,
        }
    })
    assert automatic_identity(donor) is None
