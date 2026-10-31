"""R12: self-contained reference converter tests; donor tables are never edited."""
import gzip
import json
from app.services.vehicle_directory import parse_legacy, analyze_payload, validated
from app.permissions import route_permissions
from app.route_registry import KNOWN_ROUTES

SAMPLE = """Бренды
	VOLVO
		XC90 II
			VOLVO XC90 II D5 AWD
				Год = [2015 - NULL]
				Мощность = [173 kW][235 PS]
				Обьем = 2.0
				Двигатель = diesel
				Топливо = diesel
				Кузов = [вездеход закрытый]
				Привод = [Привод на все колеса]
				Код двигателя = [D4204T23][D4204T23]
				KBA Number =
"""

def test_legacy_cp1251_preserves_unknown_year_and_codes():
    raw=SAMPLE.encode('cp1251')
    rows=list(parse_legacy(raw.decode('cp1251')))
    assert len(rows)==1
    row=validated(rows[0])
    assert (row['brand'],row['model'])==('VOLVO','XC90 II')
    assert row['year_from']==2015 and row['year_to'] is None
    assert str(row['displacement_l'])=='2.0'
    assert row['fuel_type']=='Дизель'
    assert row['drive_type']=='AWD'
    assert row['engine_codes']==['D4204T23']

def test_idempotent_content_hash_between_supported_encodings():
    raw=SAMPLE.encode('cp1251')
    converted=list(parse_legacy(SAMPLE))[0]
    data={'brand':converted['brand'],'model':converted['model'],'modification':converted['modification'],
          'year_from':converted['year_from'],'year_to':converted['year_to'],
          'displacement_l':float(converted['displacement_l']),'fuel':'Дизель',
          'power_kw':converted['power_kw'],'power_ps':converted['power_ps'],
          'body':converted['body'],'drive':converted['drive_type'],
          'engine_codes':converted['engine_codes'],'kba_numbers':converted['kba_numbers']}
    zipped=gzip.compress((json.dumps(data,ensure_ascii=False)+'\n').encode('utf-8'))
    old=analyze_payload(raw,'FileDbBMG.txt')[1]
    new=analyze_payload(zipped,'CarPot_vehicle_catalog.jsonl.gz')[1]
    assert old[0]['id']==new[0]['id']

def test_directory_routes_require_permissions():
    paths=[('GET','/api/v1/vehicle-directory/brands','vehicles.view'),
           ('GET','/api/v1/vehicle-directory/models','vehicles.view'),
           ('GET','/api/v1/vehicle-directory/variants','vehicles.view'),
           ('POST','/api/v1/vehicle-directory/import','catalog.import')]
    for method,path,permission in paths:
        assert (method,path) in KNOWN_ROUTES
        assert permission in route_permissions(method,path,{})

def test_integer_and_decimal_displacement_have_same_reference_identity():
    from app.services.vehicle_directory import validated
    r=list(parse_legacy(SAMPLE))[0]
    a=validated(dict(r,displacement_l='2'))
    b=validated(dict(r,displacement_l='2.0'))
    assert a['id']==b['id']
