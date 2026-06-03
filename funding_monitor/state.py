from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Opportunity, utc_now_iso


EMPTY_STATE = {"seen_ids": [], "opportunities": {}, "fetched_opportunities": {}, "runs": []}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(EMPTY_STATE))
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("seen_ids", [])
    state.setdefault("opportunities", {})
    state.setdefault("fetched_opportunities", {})
    state.setdefault("runs", [])
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def split_new(opportunities: list[Opportunity], state: dict[str, Any]) -> tuple[list[Opportunity], list[Opportunity]]:
    seen = set(state.get("seen_ids", []))
    new: list[Opportunity] = []
    old: list[Opportunity] = []
    for opp in opportunities:
        if opp.stable_id in seen:
            old.append(opp)
        else:
            new.append(opp)
    return new, old


def record_run(
    state: dict[str, Any],
    *,
    fetched: list[Opportunity],
    matched: list[dict[str, Any]],
    new_ids: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return state
    seen = set(state.get("seen_ids", []))
    current_fetched: dict[str, Any] = {}
    for opp in fetched:
        seen.add(opp.stable_id)
        current_fetched[opp.stable_id] = opp.to_dict()
    for item in matched:
        opp = dict(item["opportunity"])
        opp["screening"] = item.get("screening", {})
        opp["guideline_subject"] = item.get("guideline", {}).get("subject", "")
        state["opportunities"][opp["stable_id"]] = opp
        current_fetched[opp["stable_id"]] = opp
    state["seen_ids"] = sorted(seen)
    state["fetched_opportunities"] = current_fetched
    state["runs"].insert(
        0,
        {
            "fetched_at": utc_now_iso(),
            "fetched_count": len(fetched),
            "matched_count": len(matched),
            "new_count": len(new_ids),
            "new_ids": new_ids,
            "matched_ids": [item["opportunity"]["stable_id"] for item in matched],
            "fetched_ids": [opp.stable_id for opp in fetched],
        },
    )
    state["runs"] = state["runs"][:1]
    return state
