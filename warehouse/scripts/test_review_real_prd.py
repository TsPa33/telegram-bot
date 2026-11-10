"""Pure offline regression tests; no DB fixtures or external services."""
import unittest
from review_real_prd import indexed, recheck, norm, TYPES

class ReviewTests(unittest.TestCase):
    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            indexed([{'id':'1'}, {'id':'1'}], 'id')

    def test_invalid_id_rejected(self):
        with self.assertRaises(ValueError):
            indexed([{'id':'0'}], 'id')

    def test_mixed_chemical_group_restored(self):
        self.assertEqual(recheck({'screening_decision':'EXCLUDE','source_group':'Химические продукты'})[0], 'REVIEW')

    def test_tool_exclusion_remains_only_proposal(self):
        self.assertEqual(recheck({'screening_decision':'EXCLUDE','source_group':'Инструменты'}), ('EXCLUDE','inherited_proposal_not_approved'))

    def test_unknown_decision_rejected(self):
        with self.assertRaises(ValueError):
            recheck({'screening_decision':'APPROVED','source_group':''})

    def test_existing_starter_id_preserved(self):
        self.assertEqual([k for k,v in TYPES.items() if norm(v['name'])==norm('Стартер')], ['e0f9be06-1cd0-5766-99f4-677c0bbf57c7'])

if __name__ == '__main__':
    unittest.main()
