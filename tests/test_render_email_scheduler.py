import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

from funding_monitor.emailer import build_digest
from funding_monitor.render import render_site
from funding_monitor.scheduler import is_tuesday_7am_eastern


class RenderEmailSchedulerTest(unittest.TestCase):
    def test_scheduler_handles_edt(self):
        now = datetime(2026, 6, 2, 11, 0, tzinfo=timezone.utc)
        self.assertTrue(is_tuesday_7am_eastern(now))

    def test_scheduler_handles_est(self):
        now = datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(is_tuesday_7am_eastern(now))

    def test_render_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            state = {
                "runs": [
                    {
                        "fetched_at": "2026-06-02T11:00:00+00:00",
                        "fetched_count": 1,
                        "matched_count": 1,
                        "new_count": 1,
                        "matched_ids": ["abc"],
                        "fetched_ids": ["def"],
                    }
                ],
                "opportunities": {
                    "abc": {
                        "stable_id": "abc",
                        "title": "AI Materials Grant",
                        "agency": "NSF",
                        "url": "https://example.test",
                    }
                },
                "fetched_opportunities": {
                    "def": {
                        "stable_id": "def",
                        "title": "Fetched DOE Grant",
                        "agency": "DOE",
                        "url": "https://doe.example.test",
                    }
                },
            }
            render_site(path, state)
            rendered = path.read_text(encoding="utf-8")
            self.assertIn("AI Materials Grant", rendered)
            self.assertIn("Fetched Opportunities", rendered)
            self.assertIn("Fetched DOE Grant", rendered)
            self.assertIn("data-run-index=\"0\"", rendered)
            self.assertIn("selectRun", rendered)

    def test_email_digest_contains_no_duplicate_count(self):
        with patch.dict("os.environ", {"EMAIL_FROM": "sender@example.test"}):
            msg = build_digest([], "fanchem@g.clemson.edu")
        self.assertIn("0 new", msg["Subject"])
        self.assertIn("No new matched", msg.get_content())


if __name__ == "__main__":
    unittest.main()
