import unittest
from app.services.master_parts_oracle_profile import oracle_profile
from app.services.master_parts_preview import preview, read_seed
from pathlib import Path

def response(kind,car_id,items):
    return dict(source='oracle',kind=kind,source_modification_id=car_id,truncated=False,vehicle_identity_only=True,fitment_verified=False,items=[dict(attribute_type=k,display_value=v) for k,v in items])

class OracleProfileTests(unittest.TestCase):
    def test_q5(self):
        d=response('passenger',119996,[('EngineType','Бензиновый двигатель'),('FuelType','Бензин/этанол'),('BodyType','вездеход закрытый'),('DriveType','Привод на все колеса'),('NumberOfCylinders','4'),('FuelMixture','Непосредственный впрыск')]);r=oracle_profile(d,expected_kind='passenger',expected_car_id=119996);p=r['profile'];self.assertEqual(p['counts']['cylinders'],4);self.assertEqual(p['fuel'],'petrol');self.assertTrue(p['flags']['direct_injection']);self.assertNotIn('side_doors',p);self.assertNotIn('axles',p);self.assertNotIn('powertrain',p)
    def test_daf_axle_alternatives(self):
        d=response('commercial',8387,[('PlatformType','Седельный тягач'),('AxleConfiguration','4x2'),('Suspension','1 / Пневматическая рессора'),('Suspension','1 / параболическая рессора'),('Suspension','2 / Пневматическая рессора'),('EngineType','Дизель')]);r=oracle_profile(d,expected_kind='commercial',expected_car_id=8387);p=r['profile'];self.assertEqual(p['axles'],[{}, {'air_suspension':True}]);self.assertIn('axle:1:suspension_alternatives',r['conflicts']);self.assertNotIn('wheel_count_per_side',p['axles'][1]);self.assertEqual(p['body'],'tractor')
    def test_bmw_sedan(self):
        d=response('passenger',21,[('BodyType','седан'),('NumberOfCylinders','4'),('EngineType','Бензиновый двигатель'),('FuelType','бензин'),('BrakeSystem','гидравлический')]);p=oracle_profile(d,expected_kind='passenger',expected_car_id=21)['profile'];self.assertEqual(p['body'],'sedan');self.assertNotIn('side_doors',p);self.assertTrue(p['flags']['hydraulic_brakes'])
    def test_wrong_identity(self):
        d=response('passenger',21,[])
        with self.assertRaises(ValueError):oracle_profile(d,expected_kind='passenger',expected_car_id=22)
    def test_truncated(self):
        d=response('passenger',21,[]);d['truncated']=True
        with self.assertRaises(ValueError):oracle_profile(d,expected_kind='passenger',expected_car_id=21)
    def test_conflicting_cylinder_counts(self):
        d=response('passenger',21,[('NumberOfCylinders','4'),('NumberOfCylinders','6')]);r=oracle_profile(d,expected_kind='passenger',expected_car_id=21);self.assertNotIn('cylinders',r['profile']['counts']);self.assertIn('NumberOfCylinders',r['conflicts'])
    def test_partial_profile_no_fake_doors(self):
        d=response('passenger',21,[('BodyType','седан'),('EngineType','Бензиновый двигатель'),('NumberOfCylinders','4')]);p=oracle_profile(d,expected_kind='passenger',expected_car_id=21)['profile'];r=preview(read_seed(Path(__file__).resolve().parents[1]/'app/data/master_parts_seed_v02.tsv'),p);self.assertEqual(sum(x['master_key']=='piston' for x in r['positions']),4);self.assertFalse(any(x['master_key'] in ('door','headlamp','wheel') for x in r['positions']))

if __name__=='__main__':unittest.main()
