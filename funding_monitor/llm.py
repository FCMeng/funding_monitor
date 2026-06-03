from __future__ import annotations

import json
import os
from typing import Any

from .http import request_json
from .models import Guideline, Opportunity, ScreeningResult


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
SCREENING_MODEL = os.getenv("FUNDING_MONITOR_SCREENING_MODEL", "gpt-5.5")
GUIDELINE_MODEL = os.getenv("FUNDING_MONITOR_GUIDELINE_MODEL", "gpt-5.5")


SCREENING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "is_fit": {"type": "boolean"},
        "matched_profiles": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "important_info": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fit_score", "is_fit", "matched_profiles", "rationale", "important_info"],
}


GUIDELINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
}


def openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")


def call_openai_json(model: str, instructions: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    key = openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM screening/guideline generation")
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "funding_monitor_result",
                "schema": schema,
                "strict": True,
            }
        },
    }
    data = request_json(
        OPENAI_RESPONSES_URL,
        method="POST",
        payload=body,
        headers={"Authorization": f"Bearer {key}"},
        timeout=int(os.getenv("FUNDING_MONITOR_OPENAI_TIMEOUT", "90")),
    )
    text = extract_response_text(data)
    return json.loads(text)


def extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise RuntimeError(f"OpenAI response did not include output text: {data}")
    return "".join(chunks)


def screen_opportunity(opp: Opportunity, profiles: list[dict[str, Any]], *, allow_heuristic: bool = False) -> ScreeningResult:
    if allow_heuristic and not openai_key():
        return heuristic_screen(opp, profiles)
    instructions = (
        "You screen funding opportunities for a faculty researcher. "
        "Return only JSON. Mark is_fit true only when the opportunity plausibly supports at least one supplied profile, "
        "the applicant type is compatible with an academic researcher or university unless unclear, and the due date is usable or recurring. "
        "Prefer precision over recall."
    )
    result = call_openai_json(
        SCREENING_MODEL,
        instructions,
        {"opportunity": opp.to_dict(), "profiles": profiles},
        SCREENING_SCHEMA,
    )
    return ScreeningResult(
        opportunity_id=opp.stable_id,
        fit_score=int(result["fit_score"]),
        is_fit=bool(result["is_fit"]),
        matched_profiles=[str(item) for item in result["matched_profiles"]],
        rationale=str(result["rationale"]),
        important_info=[str(item) for item in result["important_info"]],
    )


def guideline_for_opportunity(
    opp: Opportunity,
    screening: ScreeningResult,
    profiles: list[dict[str, Any]],
    *,
    allow_heuristic: bool = False,
) -> Guideline:
    if allow_heuristic and not openai_key():
        return Guideline(
            opportunity_id=opp.stable_id,
            subject=f"Proposal guidance: {opp.title}",
            body=(
                f"Opportunity: {opp.title}\n\n"
                "Draft guidance could not use OpenAI because OPENAI_API_KEY is not set. "
                "Emphasize the matched research profile, connect preliminary work to the solicitation goals, "
                "identify a focused hypothesis or deliverable, and contact the program officer before submission."
            ),
        )
    instructions = (
        "Write concise, practical proposal guidance for the researcher. "
        "Use the supplied scholar profiles and opportunity facts. Include suggested project angle, aims, "
        "fit argument, team/collaboration ideas, documents to prioritize, and risks to check with the program officer."
    )
    result = call_openai_json(
        GUIDELINE_MODEL,
        instructions,
        {"opportunity": opp.to_dict(), "screening": screening.to_dict(), "profiles": profiles},
        GUIDELINE_SCHEMA,
    )
    return Guideline(opportunity_id=opp.stable_id, subject=str(result["subject"]), body=str(result["body"]))


def heuristic_screen(opp: Opportunity, profiles: list[dict[str, Any]]) -> ScreeningResult:
    text = " ".join([opp.title, opp.description, opp.agency, opp.eligibility]).lower()
    matched: list[str] = []
    hits = 0
    for profile in profiles:
        profile_hits = [kw for kw in profile.get("keywords", []) if kw.lower() in text]
        if profile_hits:
            matched.append(profile["id"])
            hits += len(profile_hits)
    agency_bonus = 10 if opp.agency.upper() in {"NSF", "DOE", "NIH", "FDA", "HHS", "SCRA"} else 0
    score = min(100, hits * 15 + agency_bonus)
    return ScreeningResult(
        opportunity_id=opp.stable_id,
        fit_score=score,
        is_fit=score >= 20,
        matched_profiles=matched,
        rationale="Heuristic keyword match used because OpenAI API key was not available.",
        important_info=["Review source page for full eligibility and required documents."],
    )
