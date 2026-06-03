import unittest

from funding_monitor.models import Opportunity
from funding_monitor.state import record_run


class StateTest(unittest.TestCase):
    def test_record_run_archives_matched_and_all_fetched_opportunities(self):
        matched = Opportunity(source="fixture", agency="NSF", title="Match", url="https://match.test")
        unmatched = Opportunity(source="fixture", agency="DOE", title="Other", url="https://other.test")
        state = {"seen_ids": [], "opportunities": {}, "fetched_opportunities": {}, "runs": []}
        record_run(
            state,
            fetched=[matched, unmatched],
            matched=[
                {
                    "opportunity": matched.to_dict(),
                    "screening": {"fit_score": 90, "matched_profiles": ["materials_ai4science"], "rationale": "Strong fit."},
                    "guideline": {"subject": "Proposal guidance"},
                }
            ],
            new_ids=[matched.stable_id],
            dry_run=False,
        )
        self.assertIn(matched.stable_id, state["seen_ids"])
        self.assertIn(unmatched.stable_id, state["seen_ids"])
        self.assertIn(matched.stable_id, state["opportunities"])
        self.assertNotIn(unmatched.stable_id, state["opportunities"])
        self.assertIn(matched.stable_id, state["fetched_opportunities"])
        self.assertIn(unmatched.stable_id, state["fetched_opportunities"])
        self.assertEqual(state["opportunities"][matched.stable_id]["screening"]["fit_score"], 90)
        self.assertEqual(state["runs"][0]["matched_ids"], [matched.stable_id])
        self.assertEqual(state["runs"][0]["fetched_ids"], [matched.stable_id, unmatched.stable_id])


if __name__ == "__main__":
    unittest.main()
