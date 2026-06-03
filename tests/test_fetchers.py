import unittest
from unittest.mock import patch

from funding_monitor.fetchers import (
    extract_grants_gov_items,
    extract_page_opportunities,
    grants_gov_item_to_opportunity,
    looks_like_funding_link,
)


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

    def test_page_link_filter_rejects_general_awards_navigation(self):
        self.assertFalse(
            looks_like_funding_link(
                "Honors & Awards",
                "https://science.osti.gov/About/Honors-and-Awards",
            )
        )

    def test_page_link_filter_keeps_specific_doe_foa(self):
        self.assertTrue(
            looks_like_funding_link(
                "Genesis Mission",
                "https://science.osti.gov/grants/FOAs/Genesis-Mission",
            )
        )

    def test_page_fetch_follows_listing_page_for_detail_links(self):
        page = {
            "name": "DOE Office of Science Funding Opportunities",
            "agency": "DOE",
            "url": "https://science.osti.gov/Funding-Opportunities",
        }
        html = """
        <a href="/About/Honors-and-Awards">Honors & Awards</a>
        <a href="/grants/FOAs/Open">Open FOAs</a>
        """
        listing_html = """
        <a href="/-/media/grants/pdf/foas/2026/DE-FOA-0003620.pdf">
          Quantum Testbeds Funding Opportunity Announcement
        </a>
        <a href="/-/media/grants/excel/2026/Application-Template.xlsx">Application Template</a>
        """
        with patch("funding_monitor.fetchers.request_text", return_value=listing_html):
            opportunities = extract_page_opportunities(html, page, page["url"])

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].title, "Quantum Testbeds Funding Opportunity Announcement")
        self.assertIn("DE-FOA-0003620.pdf", opportunities[0].url)


if __name__ == "__main__":
    unittest.main()
