from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from html import unescape
from html.parser import HTMLParser
from typing import Any, Iterable

from .http import request_json, request_text
from .models import Opportunity


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def first_value(data: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return clean_text(str(value))
    return ""


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = clean_text(" ".join(self._text))
            if text:
                self.links.append((text, self._href))
            self._href = ""
            self._text = []


def grants_gov_fetch(config: dict[str, Any]) -> list[Opportunity]:
    endpoint = config["endpoint"]
    api_key = os.getenv("GRANTS_GOV_API_KEY", "")
    headers = {"User-Agent": "funding-monitor/0.1"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key

    opportunities: dict[str, Opportunity] = {}
    close_from = date.today().isoformat()
    close_to = (date.today() + timedelta(days=370)).isoformat()
    for keyword in config.get("keywords", []):
        payload = {
            "keyword": keyword,
            "oppStatuses": "posted|forecasted",
            "rows": 50,
            "startRecordNum": 0,
            "sortBy": "closeDate|asc",
            "dateRange": f"{close_from},{close_to}",
        }
        try:
            data = request_json(endpoint, method="POST", payload=payload, headers=headers)
        except Exception as exc:
            print(f"warning: Grants.gov fetch failed for {keyword!r}: {exc}")
            continue
        for item in extract_grants_gov_items(data):
            opp = grants_gov_item_to_opportunity(item)
            opportunities[opp.stable_id] = opp
    return list(opportunities.values())


def extract_grants_gov_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [
        data.get("oppHits"),
        data.get("opportunities"),
        data.get("data", {}).get("oppHits") if isinstance(data.get("data"), dict) else None,
        data.get("data", {}).get("opportunities") if isinstance(data.get("data"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def grants_gov_item_to_opportunity(item: dict[str, Any]) -> Opportunity:
    number = first_value(item, ["number", "opportunityNumber", "fundingOpportunityNumber", "oppNum"])
    title = first_value(item, ["title", "opportunityTitle", "oppTitle"])
    agency = first_value(item, ["agency", "agencyCode", "agencyName"]) or "Grants.gov"
    synopsis_id = first_value(item, ["id", "synopsisId", "opportunityId"])
    url = first_value(item, ["url", "link"])
    if not url and synopsis_id:
        url = f"https://www.grants.gov/search-results-detail/{synopsis_id}"
    return Opportunity(
        source="Grants.gov",
        agency=agency,
        title=title or number or "Untitled Grants.gov opportunity",
        url=url or "https://www.grants.gov/search-grants",
        opportunity_number=number,
        description=first_value(item, ["description", "synopsis", "summary"]),
        amount=first_value(item, ["awardCeiling", "estimatedTotalProgramFunding", "awardFloor"]),
        due_date=first_value(item, ["closeDate", "closeDateDesc", "originalDueDate"]),
        posted_date=first_value(item, ["openDate", "postDate", "postedDate"]),
        eligibility=first_value(item, ["eligibility", "applicantEligibilityDesc"]),
        documents=infer_documents(agency, "Grants.gov"),
        raw=item,
    )


def rss_fetch(feed: dict[str, str]) -> list[Opportunity]:
    try:
        text = request_text(feed["url"])
    except Exception as exc:
        print(f"warning: RSS fetch failed for {feed['name']}: {exc}")
        return []
    root = ET.fromstring(text)
    items = root.findall(".//item")
    opportunities: list[Opportunity] = []
    for item in items[:100]:
        title = clean_text((item.findtext("title") or ""))
        link = clean_text((item.findtext("link") or feed["url"]))
        description = clean_text((item.findtext("description") or ""))
        pub_date = clean_text((item.findtext("pubDate") or ""))
        opportunities.append(
            Opportunity(
                source=feed["name"],
                agency=feed.get("agency", "NSF"),
                title=title or "Untitled RSS opportunity",
                url=link,
                description=description,
                posted_date=pub_date,
                documents=infer_documents(feed.get("agency", "NSF"), feed["name"]),
                raw={"feed": feed["url"]},
            )
        )
    return opportunities


def page_fetch(page: dict[str, str]) -> list[Opportunity]:
    try:
        text = request_text(page["url"])
    except Exception as exc:
        print(f"warning: page fetch failed for {page['name']}: {exc}")
        return []
    parser = LinkTextParser()
    parser.feed(text)
    opportunities: list[Opportunity] = []
    for title, href in parser.links:
        if not looks_like_funding_link(title, href):
            continue
        url = href
        if href.startswith("/"):
            match = re.match(r"(https?://[^/]+)", page["url"])
            if match:
                url = match.group(1) + href
        elif not href.startswith("http"):
            url = page["url"].rstrip("/") + "/" + href
        opportunities.append(
            Opportunity(
                source=page["name"],
                agency=page["agency"],
                title=title,
                url=url,
                description=f"Funding-related listing discovered on {page['name']}.",
                documents=infer_documents(page["agency"], page["name"]),
                raw={"page": page["url"]},
            )
        )
    return opportunities[:50]


def looks_like_funding_link(title: str, href: str) -> bool:
    text = f"{title} {href}".lower()
    include = ("funding", "opportun", "foa", "nofo", "grant", "rfa", "solicitation", "award")
    exclude = ("login", "privacy", "subscribe", "facebook", "twitter", "linkedin", "youtube")
    return any(word in text for word in include) and not any(word in text for word in exclude)


def infer_documents(agency: str, source: str) -> list[str]:
    text = f"{agency} {source}".upper()
    if "NSF" in text:
        return [
            "Project Summary",
            "Project Description",
            "References Cited",
            "Budget and Budget Justification",
            "Biographical Sketches",
            "Current and Pending Support",
            "Facilities, Equipment and Other Resources",
            "Data Management and Sharing Plan",
            "Mentoring Plan if required",
        ]
    if "NIH" in text or "HHS" in text or "FDA" in text:
        return [
            "SF424 (R&R) forms package",
            "Project Summary/Abstract",
            "Research Strategy",
            "Specific Aims",
            "Budget and Budget Justification",
            "NIH Biosketches",
            "Facilities and Other Resources",
            "Data Management and Sharing Plan",
            "Letters of Support if required",
        ]
    if "DOE" in text:
        return [
            "Technical volume/project narrative",
            "Budget and budget justification",
            "Biographical sketches",
            "Current and pending support",
            "Facilities and resources",
            "Data management plan",
            "Letters of commitment if required",
        ]
    if "SC" in text or "SOUTH CAROLINA" in text or "SCRA" in text:
        return [
            "Program application form",
            "Project narrative",
            "Budget",
            "Institutional approval",
            "Collaboration or industry letters if required",
        ]
    return ["Source notice", "Application package", "Budget", "Project narrative"]


def fetch_all(sources: dict[str, Any]) -> list[Opportunity]:
    opportunities: dict[str, Opportunity] = {}
    if sources.get("grants_gov", {}).get("enabled", False):
        for opp in grants_gov_fetch(sources["grants_gov"]):
            opportunities[opp.stable_id] = opp
    for feed in sources.get("rss", []):
        for opp in rss_fetch(feed):
            opportunities[opp.stable_id] = opp
    for page in sources.get("pages", []):
        for opp in page_fetch(page):
            opportunities[opp.stable_id] = opp
    return list(opportunities.values())
