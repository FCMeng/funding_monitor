import unittest
import zlib
from unittest.mock import patch

from funding_monitor.fetchers import (
    extract_grants_gov_items,
    extract_page_opportunities,
    extract_pdf_text,
    extract_solicitation_details,
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

    def test_page_link_filter_rejects_generic_navigation_titles(self):
        rejected = [
            ("Office of Sponsored Activities", "https://science.osti.gov/grants"),
            ("Funding Opportunity Announcements (FOAs)", "https://science.osti.gov/Funding-Opportunities"),
            ("Read more", "https://science.osti.gov/grants/FOAs/Genesis-Mission"),
        ]
        for title, url in rejected:
            with self.subTest(title=title):
                self.assertFalse(looks_like_funding_link(title, url))

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

    def test_page_fetch_enriches_generic_pdf_link_from_solicitation(self):
        page = {
            "name": "DOE Office of Science Funding Opportunities",
            "agency": "DOE",
            "url": "https://science.osti.gov/Funding-Opportunities",
        }
        html = '<a href="/-/media/grants/pdf/foas/2026/DE-FOA-0003620.pdf">Read more</a>'
        stream = (
            b"(Funding Opportunity Announcement Number: DE-FOA-0003620) Tj\n"
            b"(Title: Quantum Testbeds for Science) Tj\n"
            b"(Submission Deadline: July 15, 2026 at 5:00 PM ET) Tj\n"
        )
        with patch("funding_monitor.fetchers.request_bytes", return_value=b"stream\n" + zlib.compress(stream) + b"\nendstream"):
            opportunities = extract_page_opportunities(html, page, page["url"])

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].title, "Quantum Testbeds for Science")
        self.assertEqual(opportunities[0].opportunity_number, "DE-FOA-0003620")

    def test_page_fetch_strips_read_more_about_prefix(self):
        page = {
            "name": "DOE Office of Science Funding Opportunities",
            "agency": "DOE",
            "url": "https://science.osti.gov/Funding-Opportunities",
        }
        html = (
            '<a href="/-/media/grants/pdf/foas/2026/DE-FOA-0003612.pdf">'
            "Read more about The Genesis Mission: Transforming Science and Energy with AI</a>"
        )
        with patch("funding_monitor.fetchers.request_bytes", return_value=b""):
            opportunities = extract_page_opportunities(html, page, page["url"])

        self.assertEqual(opportunities[0].title, "The Genesis Mission: Transforming Science and Energy with AI")

    def test_pdf_text_and_solicitation_details_are_extracted(self):
        stream = (
            b"(Funding Opportunity Announcement Number: DE-FOA-0003620) Tj\n"
            b"(Title: Quantum Testbeds for Science) Tj\n"
            b"(Submission Deadline: July 15, 2026 at 5:00 PM ET) Tj\n"
            b"(Total Amount to be Awarded: $12,000,000) Tj\n"
            b"(Eligible Applicants: Universities and non-profit research organizations may apply.) Tj\n"
            b"(Program Description: Supports integrated quantum testbed research for scientific computing.) Tj\n"
        )
        pdf = b"stream\n" + zlib.compress(stream) + b"\nendstream"

        text = extract_pdf_text(pdf)
        details = extract_solicitation_details(text)

        self.assertEqual(details["opportunity_number"], "DE-FOA-0003620")
        self.assertEqual(details["due_date"], "July 15, 2026 at 5:00 PM ET")
        self.assertEqual(details["amount"], "$12,000,000")
        self.assertIn("Universities", details["eligibility"])
        self.assertIn("quantum testbed", details["description"])


if __name__ == "__main__":
    unittest.main()
