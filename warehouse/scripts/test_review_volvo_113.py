import copy
import json
from pathlib import Path
import unittest
from review_volvo_113 import review, summary, SECTIONS, SUBCATEGORIES

SOURCE=Path(__file__).resolve().parents[1]/'docs/universal-catalogue/volvo-113-review-proposals.json'

class VolvoReviewTests(unittest.TestCase):
    def setUp(self):
        self.source=json.loads(SOURCE.read_text())

    def test_all_ids_preserved_and_repeat_is_pure(self):
        before=copy.deepcopy(self.source)
        a=review(self.source);b=review(self.source)
        self.assertEqual(a,b);self.assertEqual(self.source,before)
        self.assertEqual({r['source_id'] for r in a},{r['source_id'] for r in self.source})
        self.assertEqual(len(a),113)
        self.assertTrue(all(r['source_id']==r['product_id'] for r in a))
        self.assertEqual({r['source_id']:r['canonical_candidate_ids'] for r in a},{r['source_id']:r['canonical_candidate_ids'] for r in self.source})

    def test_only_existing_paths_or_explicit_review(self):
        for r in review(self.source):
            self.assertIn(r['category'],SECTIONS)
            if r['subcategory']:
                self.assertIn(r['subcategory'],{x[0] for x in SUBCATEGORIES[SECTIONS.index(r['category'])]})
            else:
                self.assertEqual(r['decision'],'needs_review')
                self.assertTrue(r['unresolved_reasons'])

    def test_source_change_requires_re_review(self):
        self.source[0]['original_name']='Змінений запис'
        with self.assertRaisesRegex(ValueError,'re-review'):
            review(self.source)

    def test_ambiguous_names_not_silently_promoted(self):
        rows={r['source_id']:r for r in review(self.source)}
        for key in [38,2232,3406,4175,6331]:
            self.assertEqual(rows[key]['decision'],'needs_review')
        self.assertNotIn('Передній',rows[572]['ukrainian_name'])
        self.assertNotIn('зборі',rows[39]['ukrainian_name'])
        self.assertEqual(rows[6331]['type'],'needs_review')

    def test_duplicate_names_remain_distinct(self):
        rows={r['source_id']:r for r in review(self.source)}
        for key in [657,2070,830,2055,2394,3944]:
            self.assertTrue(rows[key]['duplicate_candidate'])
            self.assertEqual(rows[key]['decision'],'needs_review')
        self.assertEqual(len(rows),113)

    def test_usage_resolves_classification_without_physical_confirmation(self):
        rows={r['source_id']:r for r in review(self.source)}
        for key in [39,107,110,114,115,5213]:
            self.assertEqual(rows[key]['decision'],'proposed')
            self.assertNotEqual(rows[key]['applicability'],'EXPECTED')
        self.assertEqual(rows[107]['subcategory'],'Передні фари')
        self.assertEqual(rows[110]['subcategory'],'Задні ліхтарі')
        self.assertIn('прокачування',rows[5213]['ukrainian_name'])

    def test_context_change_rejected(self):
        from review_volvo_113 import CONTEXT_PATH
        context=json.loads(CONTEXT_PATH.read_text())
        context[0]['usagedescription']='Непідтверджені зміни'
        with self.assertRaisesRegex(ValueError,'checksum'):
            review(self.source,context)

    def test_no_physical_fitment_or_stock_inference(self):
        rows=review(self.source);s=summary(rows)
        self.assertEqual(s['physical_placements_verified'],0)
        self.assertEqual(s['database_writes'],0)
        self.assertFalse(s['publish_ready'])
        for r in rows:
            self.assertNotEqual(r['applicability'],'EXPECTED')
            self.assertNotEqual(r['applicability'],'INCOMPATIBLE')
            self.assertEqual(r['owner_approval'],'PENDING_OWNER_REVIEW')
            self.assertEqual(r['stock_link_status'],'UNVERIFIED_NO_DATABASE_READ')

if __name__=='__main__':unittest.main()
