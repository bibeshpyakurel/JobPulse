"""
Extract job listings from Gmail message payloads.

Each message may contain multiple job listings. The parser returns a list of
dicts with keys: title, company, link.
"""

import base64
import re
import logging
from typing import Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# --- Regex patterns -----------------------------------------------------------

# LinkedIn job alert links look like:
#   https://www.linkedin.com/comm/jobs/view/1234567890
#   https://www.linkedin.com/jobs/view/1234567890
_LINKEDIN_JOB_URL = re.compile(
    r"https://(?:www\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)[^\s\"'<>]*"
)

# Generic "Apply" / "View job" anchor text patterns
_APPLY_ANCHOR = re.compile(r"(apply|view job|see job|learn more)", re.IGNORECASE)


# --- Helpers ------------------------------------------------------------------

def _decode_part(part: dict) -> str:
    """Decode a Gmail message part body to a string."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _get_html_body(payload: dict) -> str:
    """Recursively extract the HTML body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/html":
        return _decode_part(payload)
    if "parts" in payload:
        for part in payload["parts"]:
            result = _get_html_body(part)
            if result:
                return result
    return ""


def _get_text_body(payload: dict) -> str:
    """Recursively extract the plain-text body."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        return _decode_part(payload)
    if "parts" in payload:
        for part in payload["parts"]:
            result = _get_text_body(part)
            if result:
                return result
    return ""


def _get_header(payload: dict, name: str) -> str:
    for h in payload.get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


# --- LinkedIn alert parser ----------------------------------------------------

def _parse_linkedin_html(html: str) -> list[dict]:
    """
    Parse a LinkedIn job-alert HTML email.

    LinkedIn emails structure each job as a block containing:
      - Job title in an <a> or <h3>/<strong>
      - Company + location in adjacent <span>/<p> elements
      - The job URL on the title anchor
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    # LinkedIn wraps each job in a table row or div with the job link
    for a_tag in soup.find_all("a", href=_LINKEDIN_JOB_URL):
        href = a_tag.get("href", "")
        title_text = a_tag.get_text(separator=" ", strip=True)

        if not title_text or _APPLY_ANCHOR.search(title_text):
            continue

        # Company is typically in the next sibling <span> or <p>
        company_text = ""
        parent = a_tag.find_parent(["td", "div", "li"])
        if parent:
            spans = parent.find_all(["span", "p"], limit=5)
            for span in spans:
                text = span.get_text(strip=True)
                if text and text != title_text and len(text) < 120:
                    company_text = text
                    break

        # Clean the URL (strip tracking params)
        clean_url = re.match(r"[^?]+", href).group(0)

        jobs.append({"title": title_text, "company": company_text, "link": clean_url})

    return jobs


def _parse_generic_html(html: str, subject: str) -> list[dict]:
    """
    Fallback parser for non-LinkedIn job alert emails.

    Strategy: find anchors whose text looks like a job title (not nav/footer
    boilerplate) and grab the nearest sibling text as company name.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen_links: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href: str = a_tag["href"]
        if not href.startswith("http"):
            continue
        if href in seen_links:
            continue

        title_text = a_tag.get_text(separator=" ", strip=True)
        if not title_text or len(title_text) < 5 or len(title_text) > 150:
            continue
        if _APPLY_ANCHOR.search(title_text):
            continue
        # Skip nav/footer junk
        if re.search(r"unsubscribe|privacy|terms|view in browser", title_text, re.I):
            continue

        company_text = ""
        parent = a_tag.find_parent(["td", "div", "li", "tr"])
        if parent:
            for sibling in parent.find_all(["span", "p", "td"], limit=6):
                t = sibling.get_text(strip=True)
                if t and t != title_text and 2 < len(t) < 120:
                    company_text = t
                    break

        seen_links.add(href)
        jobs.append({"title": title_text, "company": company_text, "link": href})

    return jobs


# --- Public API ---------------------------------------------------------------

def extract_jobs(message_payload: dict[str, Any]) -> list[dict]:
    """
    Given a Gmail message payload (from messages.get), return a list of job
    dicts: [{title, company, link}, ...].
    """
    html = _get_html_body(message_payload)
    subject = _get_header(message_payload, "subject")
    sender = _get_header(message_payload, "from")

    if not html:
        logger.warning("No HTML body found in message (subject=%r)", subject)
        return []

    # LinkedIn-specific parser
    if "linkedin.com" in sender.lower() or _LINKEDIN_JOB_URL.search(html):
        jobs = _parse_linkedin_html(html)
        if jobs:
            logger.info("LinkedIn parser found %d jobs (subject=%r)", len(jobs), subject)
            return jobs

    # Generic fallback
    jobs = _parse_generic_html(html, subject)
    logger.info("Generic parser found %d jobs (subject=%r)", len(jobs), subject)
    return jobs
