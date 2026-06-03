import unittest

from funding_monitor.models import Opportunity
from funding_monitor.state import load_state, split_new


class DedupTest(unittest.TestCase):
    def test_stable_id_prefers_opportunity_number(self):
        first = Opportunity(source="x", agency="NSF", title="A", url="https://one", opportunity_number="ABC")
        second = Opportunity(source="x", agency="NSF", title="B", url="https://two", opportunity_number="ABC")
        self.assertEqual(first.stable_id, second.stable_id)

    def test_split_new(self):
        opp = Opportunity(source="x", agency="DOE", title="Materials", url="https://example.test")
        state = {"seen_ids": [opp.stable_id], "opportunities": {}, "runs": []}
        new, old = split_new([opp], state)
        self.assertEqual(new, [])
        self.assertEqual(old, [opp])


if __name__ == "__main__":
    unittest.main()
