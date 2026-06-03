import unittest

from funding_monitor.llm import SCREENING_MODEL, extract_response_text, heuristic_screen
from funding_monitor.models import Opportunity


class LlmTest(unittest.TestCase):
    def test_screening_model_defaults_to_gpt_55(self):
        self.assertEqual(SCREENING_MODEL, "gpt-5.5")

    def test_extract_response_text(self):
        data = {"output": [{"content": [{"type": "output_text", "text": "{\"ok\": true}"}]}]}
        self.assertEqual(extract_response_text(data), "{\"ok\": true}")

    def test_heuristic_screen_matches_profile(self):
        opp = Opportunity(
            source="fixture",
            agency="NSF",
            title="Computational materials science and machine learning",
            url="https://example.test",
        )
        result = heuristic_screen(opp, [{"id": "p1", "keywords": ["computational materials science"]}])
        self.assertTrue(result.is_fit)
        self.assertEqual(result.matched_profiles, ["p1"])


if __name__ == "__main__":
    unittest.main()
