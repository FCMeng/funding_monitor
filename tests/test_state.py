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

    def test_record_run_replaces_stale_fetched_opportunities(self):
        stale = Opportunity(source="fixture", agency="DOE", title="Read more", url="https://old.test")
        current = Opportunity(source="fixture", agency="DOE", title="Specific notice", url="https://new.test")
        state = {
            "seen_ids": [stale.stable_id],
            "opportunities": {},
            "fetched_opportunities": {stale.stable_id: stale.to_dict()},
            "runs": [],
        }

        record_run(state, fetched=[current], matched=[], new_ids=[], dry_run=False)

        self.assertNotIn(stale.stable_id, state["fetched_opportunities"])
        self.assertIn(current.stable_id, state["fetched_opportunities"])


if __name__ == "__main__":
    unittest.main()
