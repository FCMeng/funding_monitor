import unittest

from funding_monitor.fetchers import extract_grants_gov_items, grants_gov_item_to_opportunity


class FetcherTest(unittest.TestCase):
    def test_extract_grants_gov_items_from_opp_hits(self):
        data = {"oppHits": [{"number": "NSF-1"}]}
        self.assertEqual(extract_grants_gov_items(data), [{"number": "NSF-1"}])

    def test_grants_gov_item_mapping(self):
        opp = grants_gov_item_to_opportunity(
            {
                "number": "DOE-FOA-1",
                "title": "AI for materials",
                "agency": "DOE",
                "closeDate": "2026-08-01",
                "synopsisId": "123",
            }
        )
        self.assertEqual(opp.opportunity_number, "DOE-FOA-1")
        self.assertEqual(opp.agency, "DOE")
        self.assertIn("123", opp.url)


if __name__ == "__main__":
    unittest.main()
