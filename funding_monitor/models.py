from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass(slots=True)
class Opportunity:
    source: str
    agency: str
    title: str
    url: str
    opportunity_number: str = ""
    description: str = ""
    amount: str = ""
    due_date: str = ""
    posted_date: str = ""
    eligibility: str = ""
    documents: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def stable_id(self) -> str:
        if self.opportunity_number:
            basis = f"{self.agency}:{self.opportunity_number}".lower()
        else:
            basis = f"{self.agency}:{self.title}:{self.url}".lower()
        return sha256(basis.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stable_id"] = self.stable_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Opportunity":
        fields = {
            "source",
            "agency",
            "title",
            "url",
            "opportunity_number",
            "description",
            "amount",
            "due_date",
            "posted_date",
            "eligibility",
            "documents",
            "raw",
        }
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclass(slots=True)
class ScreeningResult:
    opportunity_id: str
    fit_score: int
    is_fit: bool
    matched_profiles: list[str]
    rationale: str
    important_info: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Guideline:
    opportunity_id: str
    subject: str
    body: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
