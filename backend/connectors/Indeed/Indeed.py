"""Indeed public search pages, parsed with BeautifulSoup.

India and remote result pages are ordinary HTML. Each kept job's public
view page supplies the description. No login and no attempt to get past a block.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from Server.api import (
    Job,
    clean,
    apply_url_from_html,
    extract_experience,
    format_skills,
    is_tech_role,
    keeps_india_hybrid_or_remote,
    money_span,
    plain_text,
    split_description,
    to_datetime,
    within_days,
)
from Server.control import cancelled, pause
from Server.feeds import SidecarConnector

BASE_URL = "https://in.indeed.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IN,en;q=0.9",
}
TECH_QUERIES = (
    "software engineer",
    "software developer",
    "data engineer",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "devops engineer",
    "cloud engineer",
    "cybersecurity",
    "QA automation",
)
MAX_PAGES = 8
PAGE_SIZE = 10
_CURRENCY = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def search_url(query: str, start: int, *, remote: bool, fromage: int) -> str:
    params = {
        "q": query,
        "l": "Remote" if remote else "India",
        "fromage": str(max(1, fromage)),
        "sort": "date",
        "start": str(start),
    }
    return f"{BASE_URL}/jobs?{urlencode(params)}"


def _blocked(html: str) -> bool:
    head = (html or "")[:5000].casefold()
    return any(
        phrase in head
        for phrase in ("additional verification", "just a moment", "cf-browser-verification")
    )


def cards_from_html(html: str) -> list[dict]:
    """Job cards from a rendered Indeed search page."""
    soup = BeautifulSoup(html or "", "html.parser")
    cards = []
    seen: set[str] = set()
    for node in soup.select("div.job_seen_beacon"):
        link = node.select_one("a.jcs-JobTitle")
        if link is None:
            continue
        job_key = clean(link.get("data-jk"))
        if not job_key or job_key in seen:
            continue
        seen.add(job_key)
        company = node.select_one('[data-testid="company-name"]')
        location = node.select_one('[data-testid="text-location"]')
        salary = ""
        for snippet in node.select('[data-testid*="salary"]'):
            salary = clean(snippet.get_text(" ", strip=True))
            if salary:
                break
        cards.append({
            "title": clean(link.get_text(" ", strip=True)),
            "company": clean(company.get_text(" ", strip=True)) if company else "",
            "location": clean(location.get_text(" ", strip=True)) if location else "",
            "salary": salary,
            "url": f"{BASE_URL}/viewjob?jk={job_key}",
            "posted_at": "",
            "experience": "",
            "skill": "",
            "about": "",
            "description": "",
        })
    return cards


def _salary_text(posting: dict) -> str:
    base = posting.get("baseSalary")
    if not isinstance(base, dict):
        return ""
    value = base.get("value") or {}
    currency = clean(base.get("currency"))
    symbol = _CURRENCY.get(currency, currency or "₹")
    if not isinstance(value, dict):
        return clean(str(value))
    amount = money_span(value.get("minValue"), value.get("maxValue"), symbol)
    unit = clean(value.get("unitText"))
    if amount and unit:
        return f"{amount} a {unit.casefold()}"
    return amount


def _experience_text(posting: dict, title: str, body: str) -> str:
    raw = posting.get("experienceRequirements")
    if isinstance(raw, str) and clean(raw):
        return clean(raw)
    if isinstance(raw, dict):
        months = raw.get("monthsOfExperience")
        if months:
            years = int(months) / 12
            return f"{years:g} years"
        described = clean(raw.get("description") or "")
        if described:
            return described
    return extract_experience(title, body)


def detail_from_html(html: str, page_url: str = "") -> dict:
    """Description, date, and pay from the public job view page."""
    soup = BeautifulSoup(html or "", "html.parser")
    posting = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text() or "")
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                posting = item
                break
        if posting:
            break
    description_html = posting.get("description") or ""
    about, body = split_description(description_html)
    text = body or plain_text(description_html)
    organisation = posting.get("hiringOrganization") or {}
    company = clean(organisation.get("name")) if isinstance(organisation, dict) else ""
    places = posting.get("jobLocation") or []
    if isinstance(places, dict):
        places = [places]
    location = ""
    if places and isinstance(places[0], dict):
        address = places[0].get("address") or {}
        if isinstance(address, dict):
            location = ", ".join(
                clean(address.get(key))
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if clean(address.get(key))
            )
    title = clean(posting.get("title"))
    return {
        "title": title,
        "company": company,
        "location": location,
        "salary": _salary_text(posting),
        "posted_at": to_datetime(posting.get("datePosted")),
        "experience": _experience_text(posting, title, text),
        "skill": format_skills(posting.get("skills")),
        "about": about,
        "description": text,
        "apply": apply_url_from_html(html, page_url),
    }


class Indeed(SidecarConnector):
    key = "indeed"
    label = "Indeed"

    def iter_items(self, query: str, posted_within_days: int | None):
        selected = tuple(getattr(self, "search_phrases", ()) or ())
        if not selected:
            selected = tuple(part.strip() for part in query.split(",") if part.strip())
        searches = selected or TECH_QUERIES
        window = min(15, int(posted_within_days or 15))
        seen: set[str] = set()
        for remote in (False, True):
            for search in searches:
                if cancelled():
                    return
                for page in range(MAX_PAGES):
                    if cancelled():
                        return
                    url = search_url(search, page * PAGE_SIZE, remote=remote, fromage=window)
                    try:
                        response = requests.get(url, headers=HEADERS, timeout=30)
                        response.raise_for_status()
                    except requests.RequestException as exc:
                        self.warnings.append(f"Indeed skipped {search}: {exc}")
                        break
                    if _blocked(response.text):
                        self.warnings.append("Indeed did not return the job list")
                        return
                    cards = cards_from_html(response.text)
                    fresh = [card for card in cards if card["url"] not in seen]
                    if not fresh:
                        break
                    for card in fresh:
                        seen.add(card["url"])
                        location = card["location"] or ("Remote" if remote else "India")
                        card["location"] = location
                        if not is_tech_role(card["title"]):
                            continue
                        if not keeps_india_hybrid_or_remote(location):
                            continue
                        if pause(0.3):
                            return
                        detail = self._read_detail(card["url"])
                        for key, value in detail.items():
                            if value:
                                card[key] = value
                        posted = card.get("posted_at") or ""
                        if posted_within_days and posted and not within_days(posted, posted_within_days):
                            continue
                        yield card

    def _read_detail(self, url: str) -> dict:
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.warnings.append(f"Indeed detail skipped: {exc}")
            return {}
        if _blocked(response.text):
            self.warnings.append("Indeed did not return the job description")
            return {}
        return detail_from_html(response.text, url)

    def parse_item(self, item: dict) -> Job:
        return Job(
            source=self.label,
            title=item.get("title") or "",
            company=item.get("company") or "",
            location=item.get("location") or "",
            url=item.get("url") or "",
            posted_at=item.get("posted_at") or "",
            experience=item.get("experience") or "",
            skill=item.get("skill") or "",
            salary=item.get("salary") or "",
            about_company=item.get("about") or "",
            job_description=item.get("description") or "",
            apply_url=item.get("apply") or "",
        )
