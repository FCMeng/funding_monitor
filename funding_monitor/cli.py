from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import DATA_DIR, DOCS_DIR, load_profiles, load_sources
from .emailer import send_digest
from .fetchers import fetch_all
from .llm import guideline_for_opportunity, heuristic_screen, screen_opportunity
from .render import render_site
from .scheduler import is_tuesday_7am_eastern
from .state import load_state, record_run, save_state, split_new


STATE_PATH = DATA_DIR / "state.json"
SITE_PATH = DOCS_DIR / "index.html"
RECIPIENT = os.getenv("FUNDING_MONITOR_RECIPIENT") or os.getenv("EMAIL_TO", "fanchem@g.clemson.edu")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="funding-monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Fetch, screen, publish, and email new opportunities.")
    run_parser.add_argument("--dry-run", action="store_true", help="Do not save state or send email.")
    run_parser.add_argument("--skip-schedule-gate", action="store_true", help="Run even if it is not Tuesday 7 AM Eastern.")
    run_parser.add_argument("--skip-email", action="store_true", help="Do not send email.")
    run_parser.add_argument("--allow-heuristic", action="store_true", help="Allow heuristic screening when OPENAI_API_KEY is missing.")
    sub.add_parser("dry-run", help="Fetch and render without saving state or sending email.")
    sub.add_parser("render", help="Render the site from existing state.")
    sub.add_parser("should-run", help="Exit 0 only at Tuesday 7 AM Eastern.")
    args = parser.parse_args(argv)

    if args.command == "should-run":
        return 0 if is_tuesday_7am_eastern() else 1
    if args.command == "render":
        state = load_state(STATE_PATH)
        render_site(SITE_PATH, state)
        print(f"rendered {SITE_PATH}")
        return 0
    if args.command == "dry-run":
        args.command = "run"
        args.dry_run = True
        args.skip_schedule_gate = True
        args.skip_email = True
        args.allow_heuristic = True

    if args.command == "run":
        return run_pipeline(
            dry_run=args.dry_run,
            skip_schedule_gate=args.skip_schedule_gate,
            skip_email=args.skip_email,
            allow_heuristic=args.allow_heuristic or os.getenv("FUNDING_MONITOR_ALLOW_HEURISTIC") == "1",
        )
    raise AssertionError(f"unhandled command {args.command}")


def run_pipeline(*, dry_run: bool, skip_schedule_gate: bool, skip_email: bool, allow_heuristic: bool) -> int:
    if not skip_schedule_gate and not is_tuesday_7am_eastern():
        print("Not Tuesday 7 AM Eastern; exiting without changes.")
        return 0

    profiles = load_profiles()
    sources = load_sources()
    state = load_state(STATE_PATH)
    fetched = fetch_all(sources)
    new_opps, _old_opps = split_new(fetched, state)
    print(f"Fetched {len(fetched)} opportunities; {len(new_opps)} not seen before.")

    matches: list[dict] = []
    candidate_opps = prefilter_opportunities(new_opps, profiles)
    max_screens = int(os.getenv("FUNDING_MONITOR_MAX_LLM_SCREENS", "30"))
    if len(candidate_opps) > max_screens:
        print(f"Prefilter kept {len(candidate_opps)} candidates; screening first {max_screens}.", flush=True)
        candidate_opps = candidate_opps[:max_screens]
    else:
        print(f"Prefilter kept {len(candidate_opps)} candidates for LLM screening.", flush=True)

    for index, opp in enumerate(candidate_opps, start=1):
        print(f"Screening {index}/{len(candidate_opps)}: {opp.title[:100]}", flush=True)
        screening = screen_opportunity(opp, profiles, allow_heuristic=allow_heuristic)
        if not screening.is_fit:
            continue
        print(f"Generating guideline for: {opp.title[:100]}", flush=True)
        guideline = guideline_for_opportunity(opp, screening, profiles, allow_heuristic=allow_heuristic)
        matches.append(
            {
                "opportunity": opp.to_dict(),
                "screening": screening.to_dict(),
                "guideline": guideline.to_dict(),
            }
        )

    new_ids = [item["opportunity"]["stable_id"] for item in matches]
    state = record_run(state, fetched=fetched, matched=matches, new_ids=new_ids, dry_run=dry_run)
    render_state = preview_state(state, matches) if dry_run else state
    render_site(SITE_PATH, render_state, latest_matches=matches)
    if not dry_run:
        save_state(STATE_PATH, state)
    if matches and not skip_email and not dry_run:
        try:
            send_digest(matches, RECIPIENT)
            print(f"Sent digest to {RECIPIENT}.")
        except Exception as exc:
            print(f"warning: email delivery failed after site/state generation: {exc}", flush=True)
    elif not matches:
        print("No new matched opportunities to email.")
    print(f"Rendered site at {Path(SITE_PATH)}")
    return 0


def prefilter_opportunities(opportunities: list, profiles: list[dict]) -> list:
    ranked = []
    for opp in opportunities:
        screening = heuristic_screen(opp, profiles)
        if screening.fit_score <= 0:
            continue
        ranked.append((screening.fit_score, opp))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [opp for _score, opp in ranked]


def preview_state(state: dict, matches: list[dict]) -> dict:
    preview = {
        "seen_ids": list(state.get("seen_ids", [])),
        "opportunities": dict(state.get("opportunities", {})),
        "runs": list(state.get("runs", [])),
    }
    for item in matches:
        opp = dict(item["opportunity"])
        opp["screening"] = item.get("screening", {})
        opp["guideline_subject"] = item.get("guideline", {}).get("subject", "")
        preview["opportunities"][opp["stable_id"]] = opp
    if matches:
        preview["runs"].insert(
            0,
            {
                "fetched_at": "dry-run preview",
                "fetched_count": len(matches),
                "matched_count": len(matches),
                "new_count": len(matches),
            },
        )
    return preview


if __name__ == "__main__":
    raise SystemExit(main())
