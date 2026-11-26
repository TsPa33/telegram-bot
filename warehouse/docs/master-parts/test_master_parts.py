import copy, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"backend"))
from app.services.master_parts_preview import read_seed, preview
from audit import fixture, axle

ENTRIES=read_seed(Path(__file__).resolve().parents[2]/'backend/app/data/master_parts_seed_v02.tsv')
def positions(r,key):return {x['placement'] for x in r['positions'] if x['master_key']==key}

class MasterPartsTests(unittest.TestCase):
    def test_suv(self):
        r=preview(ENTRIES,fixture());self.assertEqual(positions(r,'door'),{'door:FL','door:FR','door:RL','door:RR'});self.assertEqual(positions(r,'trunk_lid'),{'rear:liftgate'});self.assertEqual(len(positions(r,'door_hinge')),8);self.assertEqual(len(positions(r,'mirror')),2)
    def test_sedan(self):self.assertEqual(positions(preview(ENTRIES,fixture('sedan',rear='lid')),'trunk_lid'),{'rear:lid'})
    def test_coupe(self):
        r=preview(ENTRIES,fixture('coupe',doors=('FL','FR'),rear='lid'));self.assertEqual(len(positions(r,'door')),2);self.assertEqual(len(positions(r,'window_regulator')),2)
    def test_coupe_conflict(self):
        with self.assertRaises(ValueError):preview(ENTRIES,fixture('coupe'))
    def test_hatch(self):self.assertEqual(len(positions(preview(ENTRIES,fixture('hatch',doors=('FL','FR'))),'door')),2)
    def test_van(self):
        r=preview(ENTRIES,fixture('van','lcv',doors=('FL','FR','SR'),rear='split'));self.assertEqual(len(positions(r,'door')),3);self.assertEqual(positions(r,'trunk_lid'),{'rear:door:L','rear:door:R'})
    def test_4x2(self):
        p=fixture('tractor','heavy_truck',doors=('FL','FR'),rear='none',axles=[axle(steered=True),axle(driven=True,disc=False,dual=True,air=True,coil=False,independent=False)]);r=preview(ENTRIES,p);self.assertEqual(len(positions(r,'wheel')),6);self.assertEqual(len(positions(r,'cab_door')),2);self.assertFalse(positions(r,'door'));self.assertEqual(positions(r,'brake_disc'),{'axle:1:L','axle:1:R'});self.assertEqual(positions(r,'brake_drum'),{'axle:2:L','axle:2:R'});self.assertEqual(positions(r,'brake_pad'),{'axle:1'});self.assertEqual(positions(r,'brake_shoe'),{'axle:2'})
    def test_6x4(self):
        p=fixture('tractor','heavy_truck',doors=('FL','FR'),rear='none',axles=[axle(steered=True),axle(driven=True,dual=True),axle(driven=True,dual=True)]);r=preview(ENTRIES,p);self.assertEqual(len(positions(r,'wheel')),10);self.assertEqual(positions(r,'differential'),{'axle:2','axle:3'})
    def test_bev(self):
        r=preview(ENTRIES,fixture(powertrain='BEV'));self.assertFalse(positions(r,'engine'));self.assertFalse(positions(r,'spark_plug'));self.assertTrue(positions(r,'battery'));self.assertTrue(positions(r,'hv_battery'))
    def test_phev(self):
        r=preview(ENTRIES,fixture(powertrain='PHEV'));self.assertTrue(positions(r,'engine'));self.assertTrue(positions(r,'hv_battery'));self.assertTrue(positions(r,'charge_port'));self.assertFalse(positions(r,'alternator'))
    def test_unknown(self):self.assertFalse(preview(ENTRIES,{})['positions'])
    def test_unknown_axle_features(self):
        p=fixture();p['axles'][1]['disc_brakes']=None;r=preview(ENTRIES,p);self.assertEqual(len(positions(r,'brake_disc')),2);self.assertTrue(any(x['master_key']=='brake_disc' for x in r['review']))
    def test_set_per_axle(self):self.assertEqual(len(positions(preview(ENTRIES,fixture()),'brake_pad')),2)
    def test_ice_counts(self):self.assertEqual(len(positions(preview(ENTRIES,fixture()),'piston')),4)
    def test_repeat(self):
        p=fixture();s=[{'product_id':530,'oem':'old'}];prior=copy.deepcopy(s);a=preview(ENTRIES,p,s);b=preview(ENTRIES,p,s);self.assertEqual(a,b);self.assertEqual(s,prior);self.assertEqual(len(a['positions']),len({(x['master_key'],x['placement']) for x in a['positions']}))
    def test_generic_not_duplicated(self):
        r=preview(ENTRIES,fixture(),[{'product_id':530}]);self.assertTrue(all(x['state']=='reconcile' for x in r['positions'] if x['master_key']=='door'))
    def test_existing_preserved(self):
        old=[{'master_key':'door','placement':'door:FL','part_id':'stock','oem':'manual'}];r=preview(ENTRIES,fixture(),existing_rows=old);self.assertEqual(r['existing_rows'],old);self.assertEqual(next(x['state'] for x in r['positions'] if x['master_key']=='door' and x['placement']=='door:FL'),'existing')
    def test_unmapped_legacy_blocks(self):self.assertNotIn('supplement_candidate',preview(ENTRIES,fixture(),existing_rows=[{'part_id':'stock'}])['counts'])
    def test_oem_requires_graph_and_position(self):
        ident=dict(kind='passenger',manufacturer_id=5,model_id=7534,car_id=119996,snapshot_sha='a'*64);src=[{'product_id':530,'articles':[{'supplier_id':1,'article_nr':'ART','oem_numbers':['OE-L'],'verified_placements':['door:FL']}]}];ev=dict(identity=ident,master_key='door',placement='door:FL',product_id=530,supplier_id=1,article_number='ART',oem='OE-L',placement_verified=True)
        r=preview(ENTRIES,fixture(),src,identity=ident,position_evidence=[ev,{**ev,'placement':'door:FR'},{**ev,'oem':'FAKE'},{**ev,'article_number':'WRONG'},{**ev,'identity':{**ident,'car_id':1}}]);codes={x['placement']:x['proposed_oem'] for x in r['positions'] if x['master_key']=='door'};self.assertEqual(codes,{'door:FL':'OE-L','door:FR':None,'door:RL':None,'door:RR':None});self.assertTrue(all(x['oem'] is None for x in r['positions']))
    def test_oem_unknown_source(self):self.assertTrue(all(x['proposed_oem'] is None for x in preview(ENTRIES,fixture(),[{'product_id':530,'oem':'UNPLACED'}])['positions']))
    def test_unknown_door_feature(self):
        p=fixture();p['door_features'].pop('door_glass');r=preview(ENTRIES,p);self.assertFalse(positions(r,'door_glass'));self.assertTrue(positions(r,'door'))
    def test_seed_mapping(self):self.assertEqual(len(ENTRIES),166)

if __name__=='__main__':unittest.main()
