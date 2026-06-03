from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
import zlib
from datetime import date, timedelta
from html import unescape
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urldefrag, urlparse

from .http import request_bytes, request_json, request_text
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
    return extract_page_opportunities(text, page, page["url"])


def extract_page_opportunities(text: str, page: dict[str, str], base_url: str, *, depth: int = 0) -> list[Opportunity]:
    parser = LinkTextParser()
    parser.feed(text)
    opportunities: dict[str, Opportunity] = {}
    listing_urls: dict[str, str] = {}
    for title, href in parser.links:
        url = normalize_link(base_url, href)
        if not url:
            continue
        if is_opportunity_detail_link(title, url):
            opp = page_link_to_opportunity(page, title, url, base_url)
            opportunities[opp.stable_id] = opp
        elif depth == 0 and is_opportunity_listing_link(title, url):
            listing_urls[url] = title

    if depth == 0:
        for listing_url in list(listing_urls)[:8]:
            try:
                listing_text = request_text(listing_url)
            except Exception as exc:
                print(f"warning: deeper page fetch failed for {listing_url}: {exc}")
                continue
            for opp in extract_page_opportunities(listing_text, page, listing_url, depth=1):
                opportunities[opp.stable_id] = opp
    return list(opportunities.values())[:50]


def looks_like_funding_link(title: str, href: str) -> bool:
    url = normalize_link("https://example.test", href) or href
    return is_opportunity_detail_link(title, url) or is_opportunity_listing_link(title, url)


def normalize_link(base_url: str, href: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith("#"):
        return ""
    scheme = urlparse(href).scheme.lower()
    if scheme in {"mailto", "tel", "javascript"}:
        return ""
    url, _fragment = urldefrag(urljoin(base_url, href))
    return url


def page_link_to_opportunity(page: dict[str, str], title: str, url: str, source_url: str) -> Opportunity:
    prefer_extracted_title = is_generic_link_title(title)
    opp = Opportunity(
        source=page["name"],
        agency=page["agency"],
        title=clean_opportunity_title(title, url),
        url=url,
        description=f"Funding opportunity detail discovered on {page['name']}.",
        documents=infer_documents(page["agency"], page["name"]),
        raw={"page": source_url},
    )
    if is_pdf_url(url):
        enrich_pdf_opportunity(opp, prefer_extracted_title=prefer_extracted_title)
    return opp


def clean_opportunity_title(title: str, url: str) -> str:
    title = clean_text(title)
    title = re.sub(r"^read more about\s+", "", title, flags=re.IGNORECASE)
    if title and not is_generic_link_title(title):
        return title
    filename = urlparse(url).path.rsplit("/", 1)[-1]
    filename = re.sub(r"\.[a-z0-9]+$", "", filename, flags=re.IGNORECASE)
    filename = filename.replace("-", " ").replace("_", " ")
    return clean_text(filename).title() or "Untitled funding opportunity"


def is_opportunity_detail_link(title: str, url: str) -> bool:
    text = f"{title} {url}".lower()
    parsed = urlparse(url)
    path = parsed.path.lower()
    if has_excluded_link_terms(text, path):
        return False
    if is_generic_link_title(title) and not is_pdf_url(url):
        return False
    if path.rstrip("/").endswith(("/grants/foas/open", "/grants/lab-announcements/open")):
        return False
    if "/grants/foas/" in path and not path.rstrip("/").endswith("/open"):
        return True
    if "/-/media/grants/pdf/foas/" in path:
        return True
    if "/-/media/grants/pdf/lab-announcements/" in path:
        return True
    if "/funding/opportunities/" in path and not path.rstrip("/").endswith("/funding/opportunities"):
        return True
    include = ("funding opportunity", "grant", "rfa", "solicitation", "research program")
    return any(word in text for word in include) and not is_general_funding_page(path)


def is_opportunity_listing_link(title: str, url: str) -> bool:
    text = f"{title} {url}".lower()
    path = urlparse(url).path.lower().rstrip("/")
    if has_excluded_link_terms(text, path):
        return False
    if is_generic_link_title(title) and not path.endswith(("/grants/foas/open", "/grants/lab-announcements/open")):
        return False
    if path.endswith(("/grants/foas/open", "/grants/lab-announcements/open")):
        return True
    if path.endswith(("/funding-opportunities", "/get-research-funding", "/get-startup-funding")):
        return True
    return False


def has_excluded_link_terms(text: str, path: str) -> bool:
    include = ("funding", "opportun", "foa", "nofo", "grant", "rfa", "solicitation", "award")
    exclude = (
        "login",
        "privacy",
        "subscribe",
        "facebook",
        "twitter",
        "linkedin",
        "youtube",
        "honors-and-awards",
        "honors & awards",
        "award search",
        "public abstracts",
        "interactive-grants-map",
        "acknowledgement",
        "digital-data-management",
        "webinar",
        "slides",
        "video",
        "faq",
        "frequently asked",
        "template",
        "sample",
        "email-protection",
        "office of sponsored activities",
        "sponsored activities",
        "grants policy",
        "contract information",
        "applicant and awardee resources",
    )
    resource_ext = (".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx")
    return (
        not any(word in text for word in include)
        or any(word in text for word in exclude)
        or path.endswith(resource_ext)
    )


def is_generic_link_title(title: str) -> bool:
    normalized = clean_text(title).lower()
    generic_titles = {
        "",
        "read more",
        "more",
        "learn more",
        "here",
        "available here",
        "html",
        "pdf",
        "foa",
        "foas",
        "funding opportunity announcement",
        "funding opportunity announcements",
        "funding opportunity announcements (foas)",
        "office of sponsored activities",
    }
    return normalized in generic_titles


def is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def enrich_pdf_opportunity(opp: Opportunity, *, prefer_extracted_title: bool = False) -> None:
    try:
        pdf_text = extract_pdf_text(request_bytes(opp.url))
    except Exception as exc:
        opp.raw["pdf_error"] = str(exc)
        return
    if not pdf_text:
        return
    details = extract_solicitation_details(pdf_text)
    opp.raw["pdf_excerpt"] = pdf_text[:4000]
    if details.get("title") and (prefer_extracted_title or is_generic_link_title(opp.title)):
        opp.title = details["title"]
    if details.get("opportunity_number"):
        opp.opportunity_number = details["opportunity_number"]
    if details.get("due_date"):
        opp.due_date = details["due_date"]
    if details.get("posted_date"):
        opp.posted_date = details["posted_date"]
    if details.get("amount"):
        opp.amount = details["amount"]
    if details.get("eligibility"):
        opp.eligibility = details["eligibility"]
    if details.get("description"):
        opp.description = details["description"]


def extract_pdf_text(data: bytes) -> str:
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.DOTALL):
        stream = match.group(1)
        for candidate in (stream, try_decompress(stream)):
            if not candidate:
                continue
            text = extract_pdf_stream_text(candidate)
            if text:
                chunks.append(text)
    return clean_text(" ".join(chunks))


def try_decompress(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except Exception:
        return b""


def extract_pdf_stream_text(data: bytes) -> str:
    text_parts: list[str] = []
    for match in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj", data, flags=re.DOTALL):
        text_parts.append(decode_pdf_literal(match.group(0).rsplit(b")", 1)[0] + b")"))
    for match in re.finditer(rb"\[(.*?)\]\s*TJ", data, flags=re.DOTALL):
        text_parts.extend(decode_pdf_literal(item) for item in re.findall(rb"\((?:\\.|[^\\()])*\)", match.group(1)))
    return " ".join(part for part in text_parts if part)


def decode_pdf_literal(value: bytes) -> str:
    if value.startswith(b"(") and value.endswith(b")"):
        value = value[1:-1]
    value = re.sub(rb"\\([()\\])", rb"\1", value)
    value = re.sub(rb"\\n", b"\n", value)
    value = re.sub(rb"\\r", b"\r", value)
    value = re.sub(rb"\\t", b"\t", value)
    return value.decode("latin-1", errors="ignore")


def extract_solicitation_details(text: str) -> dict[str, str]:
    details: dict[str, str] = {}
    number = first_regex(
        text,
        [
            r"(?:Funding Opportunity Announcement|FOA|NOFO|LAB) Number[:\s]+([A-Z]{1,4}[- ][A-Z0-9]{2,}[- ][0-9]{3,}(?:[- ][0-9]{6})?)",
            r"\b((?:DE-FOA|LAB)-\d{4}-\d{4,}(?:-\d{6})?)\b",
        ],
    )
    if number:
        details["opportunity_number"] = number.replace(" ", "-")
    title = first_regex(
        text,
        [
            r"Title[:\s]+(.+?)(?:\s+(?:Submission Deadline|Application Deadline|Total Amount to be Awarded|Eligible Applicants|Program Description|Description|Summary)[:\s]|$)",
            r"(?:Funding Opportunity Announcement|Announcement)\s+(?:Number[:\s]+[A-Z0-9-]+)?\s+([A-Z][A-Za-z0-9 ,:/&()'\".-]{20,160})",
        ],
    )
    if title:
        details["title"] = clean_text(title)
    due_date = first_regex(
        text,
        [
            r"(?:Submission Deadline|Application Deadline|Deadline for Applications|Full Application Due Date|Due Date)[:\s]+([A-Z][A-Za-z]+ \d{1,2}, \d{4}(?:,? at [0-9: .]+[AP]M(?:\s(?:ET|EDT|EST|CT|MT|PT))?)?)",
            r"(?:Full Application|Applications?)[:\s]+(?:due\s*)?([A-Z][A-Za-z]+ \d{1,2}, \d{4})",
        ],
    )
    if due_date:
        details["due_date"] = clean_text(due_date)
    posted = first_regex(text, [r"(?:Issue Date|Posted Date|Date Issued)[:\s]+([A-Z][A-Za-z]+ \d{1,2}, \d{4})"])
    if posted:
        details["posted_date"] = posted
    amount = first_regex(
        text,
        [
            r"(?:Total Amount to be Awarded|Estimated Funding|Award Ceiling|Total Funding)[:\s]+(\$[0-9][0-9,]*(?:\s*(?:million|M))?)",
            r"approximately (\$[0-9][0-9,]*(?:\s*(?:million|M))?)",
        ],
    )
    if amount:
        details["amount"] = clean_text(amount)
    eligibility = section_excerpt(text, ["Eligible Applicants", "Eligibility", "Applicant Eligibility"], 360)
    if eligibility:
        details["eligibility"] = eligibility
    synopsis = section_excerpt(text, ["Program Description", "Description", "Summary", "Purpose"], 700)
    if synopsis:
        details["description"] = synopsis
    return details


def first_regex(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    return ""


def section_excerpt(text: str, headings: list[str], limit: int) -> str:
    for heading in headings:
        match = re.search(rf"{re.escape(heading)}[:\s]+(.{{20,{limit * 2}}})", text, flags=re.IGNORECASE)
        if match:
            excerpt = re.split(
                r"\s(?:Table of Contents|Section [IVX]+|[A-Z][A-Za-z ]{3,35}:)\s",
                match.group(1),
                maxsplit=1,
            )[0]
            return clean_text(excerpt)[:limit].rstrip(" ,;:-")
    return ""


def is_general_funding_page(path: str) -> bool:
    path = path.lower().rstrip("/")
    return path.endswith(
        (
            "/funding-opportunities",
            "/funding-opportunities/find-funding",
            "/funding-opportunities/award",
            "/get-support/get-research-funding",
            "/get-support/get-startup-funding",
        )
    )


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
