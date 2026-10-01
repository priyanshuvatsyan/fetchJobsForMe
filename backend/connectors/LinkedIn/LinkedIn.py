"""Public LinkedIn guest search for tech roles in India or remote."""

from __future__ import annotations

import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from Server.control import pause, stale, token
from Server.feeds import get_store
from Server.api import (
    Job,
    clean,
    extract_salary,
    is_tech_role,
    job_profile,
    keeps_india_hybrid_or_remote,
    money_span,
    plain_text,
    split_description,
    to_datetime,
    within_days,
)
MIN_DELAY = 1.0
MAX_DELAY = 10.0
BASE_URL = "https://www.linkedin.com"
SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/"
    "seeMoreJobPostings/search"
)
STORE = get_store("linkedin")
JOBS_FILE = STORE.path

# One guest-search query that covers software, data, and ML roles.
TECH_KEYWORDS = (
    "software engineer OR software developer OR developer OR "
    "data analyst OR devops OR mlops OR "
    "machine learning engineer OR AI engineer"
)

# India (onsite and hybrid), Indian hybrid, and remote work anywhere.
SEARCHES = (
    {
        "label": "India",
        "params": {"location": "India", "geoId": "102713980"},
        "remote": False,
    },
    {
        "label": "India hybrid",
        "params": {"location": "India", "geoId": "102713980", "f_WT": "3"},
        "remote": False,
    },
    {
        "label": "Remote",
        "params": {"f_WT": "2"},
        "remote": True,
    },
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_session = requests.Session()
_session.headers.update(HEADERS)


def random_delay() -> bool:
    """Wait between guest requests. Return True if the fetch was cancelled."""
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    print(f"Waiting {delay:.1f} seconds...")
    return pause(delay)


def _soup(response: requests.Response) -> BeautifulSoup:
    return BeautifulSoup(response.text, "html.parser")


def get_job_cards(start: int = 0, extra: dict | None = None) -> list:
    params = {"start": start, "keywords": TECH_KEYWORDS}
    if extra:
        params.update(extra)
    response = _session.get(SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    return _soup(response).select("li")


def _first_text(node, selectors: list[str]) -> str:
    if node is None:
        return ""
    for selector in selectors:
        element = node.select_one(selector)
        if not element:
            continue
        text = clean(element.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _relative_posted(text: str) -> str:
    folded = (text or "").casefold()
    if not folded:
        return ""
    if any(word in folded for word in ("just now", "today", "hour", "minute")):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    match = re.search(r"(\d+)\+?\s*(day|week|month)s?\s+ago", folded)
    if not match:
        return ""
    count = int(match.group(1))
    unit = match.group(2)
    days = count if unit == "day" else count * 7 if unit == "week" else count * 30
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _posted_from_node(node) -> str:
    if node is None:
        return ""
    for element in node.select("time"):
        stamped = to_datetime(element.get("datetime"))
        if stamped:
            return stamped
        stamped = _relative_posted(element.get_text(" ", strip=True))
        if stamped:
            return stamped
    return _relative_posted(node.get_text(" ", strip=True)[:240])


def extract_basic_job(card) -> dict:
    link = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
    url = ""
    if link and link.get("href"):
        url = link.get("href").split("?")[0]
        if url.startswith("/"):
            url = urljoin(BASE_URL, url)
    return {
        "title": _first_text(card, ["h3.base-search-card__title", "h3"]),
        "company": _first_text(card, ["h4.base-search-card__subtitle", ".base-search-card__subtitle", "h4"]),
        "location": _first_text(card, [".job-search-card__location", ".base-search-card__metadata"]),
        "posted_at": _posted_from_node(card),
        "url": url,
    }


def _walk_postings(value) -> list[dict]:
    found = []
    if isinstance(value, list):
        for item in value:
            found.extend(_walk_postings(item))
        return found
    if not isinstance(value, dict):
        return found
    kind = value.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    if "JobPosting" in kinds:
        found.append(value)
    for child in value.values():
        if isinstance(child, (dict, list)):
            found.extend(_walk_postings(child))
    return found


def embedded_posting(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script"):
        raw = script.string or script.get_text() or ""
        if "JobPosting" not in raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _walk_postings(payload)
        if found:
            return found[0]
    return {}


def _labeled_values(soup: BeautifulSoup) -> list[tuple[str, str]]:
    pairs = []
    blocks = soup.select(
        ".description__job-criteria-item, li, [class*='criterion'], [class*='insight'], [class*='job-criteria']"
    )
    for block in blocks:
        label = _first_text(
            block,
            ["h3", "dt", "[class*='subheader']", "[class*='label']", "strong"],
        )
        value = _first_text(
            block,
            ["span", "dd", "[class*='criteria-text']", "[class*='value']"],
        )
        if not value:
            value = clean(block.get_text(" ", strip=True))
            if label and value.lower().startswith(label.lower()):
                value = clean(value[len(label):].lstrip(":- "))
        if label and value and label.casefold() != value.casefold():
            pairs.append((label, value))
    return pairs


def _value_for(pairs: list[tuple[str, str]], *words: str) -> str:
    for label, value in pairs:
        folded = label.casefold()
        if any(word in folded for word in words) and len(value) <= 180:
            return value
    return ""


def _skill_text(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        return clean(value.get("name") or value.get("skill") or "")
    if isinstance(value, list):
        parts = [_skill_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    return ""


def _experience_text(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        months = value.get("monthsOfExperience")
        if months:
            years = float(months) / 12
            if years >= 1 and years == int(years):
                return f"{int(years)} years"
            if years > 0:
                return f"{years:.1f} years"
        return clean(value.get("description") or value.get("name") or "")
    if isinstance(value, list):
        return ", ".join(part for part in (_experience_text(item) for item in value) if part)
    return ""


def _salary_text(posting: dict, soup: BeautifulSoup, body: str) -> str:
    base = posting.get("baseSalary") or posting.get("estimatedSalary") or {}
    if isinstance(base, str):
        stated = extract_salary("", base)
        if stated:
            return stated
    if isinstance(base, dict):
        currency = clean(base.get("currency") or "INR")
        symbol = {"USD": "$", "GBP": "£", "EUR": "€", "INR": "₹"}.get(currency, f"{currency} ")
        value = base.get("value") or {}
        if isinstance(value, dict):
            span = money_span(value.get("minValue"), value.get("maxValue"), symbol)
            if span:
                return span
        stated = extract_salary("", clean(base.get("name") or ""))
        if stated:
            return stated
    for _label, value in _labeled_values(soup):
        if extract_salary("", value):
            return extract_salary("", value)
    return extract_salary(body)


def _description_text(posting: dict, soup: BeautifulSoup) -> str:
    embedded = posting.get("description") or ""
    if isinstance(embedded, str) and clean(plain_text(embedded)):
        return embedded
    text = _first_text(
        soup,
        [
            ".show-more-less-html__markup",
            ".show-more-less-html",
            ".description__text",
            ".jobs-description__content",
            ".jobs-box__html-content",
            "[class*='description']",
            "article",
            "main",
        ],
    )
    return text


def extract_job_details(url: str, card_posted: str = "") -> dict:
    print(f"Fetching job details:\n{url}")
    empty = {
        "experience": "",
        "skill": "",
        "salary": "",
        "about_company": "",
        "job_description": "",
        "posted_at": card_posted,
    }
    try:
        response = _session.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Failed to fetch job: {error}")
        return empty

    soup = _soup(response)
    posting = embedded_posting(soup)
    body = _description_text(posting, soup)
    about_company, job_description = split_description(plain_text(body) if "<" in body else body)
    pairs = _labeled_values(soup)
    listed_skills = _skill_text(posting.get("skills"))
    if not listed_skills:
        listed_skills = _value_for(pairs, "skill")
    experience = _experience_text(posting.get("experienceRequirements"))
    if not experience:
        experience = _value_for(pairs, "experience", "seniority", "level")
    plain_body = plain_text(body)
    if not experience or not listed_skills:
        guessed_experience, guessed_skills = job_profile("", plain_body, None)
        experience = experience or guessed_experience
        listed_skills = listed_skills or guessed_skills
    if not listed_skills:
        match = re.search(
            r"(?i)(?:skills|tech stack|technologies|tools)\s*[:\-]\s*(.{3,240})",
            plain_body,
        )
        if match:
            listed_skills = clean(match.group(1).split(".")[0])
    posted = (
        to_datetime(posting.get("datePosted"))
        or _posted_from_node(soup)
        or card_posted
    )
    return {
        "experience": experience,
        "skill": listed_skills,
        "salary": _salary_text(posting, soup, plain_text(body)),
        "about_company": about_company,
        "job_description": job_description or plain_text(body),
        "posted_at": posted,
    }


class LinkedIn:
    key = "linkedin"
    label = "LinkedIn"
    persist = "sidecar"

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.search_url = ""

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 0,
        boards: list[str] | None = None,
        open_browser: bool = False,
        on_batch=None,
        posted_within_days: int | None = None,
    ) -> list[Job]:
        del boards, open_browser
        self.warnings = []
        cap = None if limit <= 0 else limit
        keywords = query.strip() or TECH_KEYWORDS
        place = where.strip()
        jobs: list[Job] = []
        seen_urls: set[str] = set()
        page_size = 25
        started = token()
        epoch = STORE.reset()

        searches = SEARCHES
        if place:
            searches = (
                {
                    "label": place,
                    "params": {"location": place},
                    "remote": place.casefold() == "remote",
                },
            )

        try:
            self._collect(
                searches, keywords, jobs, seen_urls, page_size, cap,
                posted_within_days, on_batch, started, epoch,
            )
        finally:
            if STORE.epoch == epoch:
                STORE.flush()

        print()
        print(f"Saved {len(jobs)} jobs")
        print(f"File: {JOBS_FILE}")
        return jobs

    def _collect(
        self,
        searches,
        keywords: str,
        jobs: list[Job],
        seen_urls: set[str],
        page_size: int,
        cap: int | None,
        posted_within_days: int | None,
        on_batch,
        started: int,
        epoch: int,
    ) -> None:
        for search in searches:
            if stale(started):
                return
            start = 0
            while cap is None or len(jobs) < cap:
                if stale(started):
                    return
                print()
                print("=" * 70)
                print(f"SEARCH        : {search['label']}")
                print(f"KEYWORDS      : {keywords}")
                print(f"SEARCH OFFSET : {start}")
                print(f"JOBS COLLECTED: {len(jobs)}" + (f"/{cap}" if cap else ""))
                print("=" * 70)
                params = dict(search["params"])
                params["keywords"] = keywords
                if posted_within_days:
                    params["f_TPR"] = f"r{int(posted_within_days) * 86400}"
                try:
                    cards = get_job_cards(start=start, extra=params)
                except requests.RequestException as error:
                    print(f"Search request failed: {error}")
                    self.warnings.append(str(error))
                    break
                if not cards:
                    print("No more search results.")
                    break

                new_jobs = 0
                for card in cards:
                    if stale(started) or (cap is not None and len(jobs) >= cap):
                        break
                    basic = extract_basic_job(card)
                    url = basic["url"]
                    if not url or url in seen_urls:
                        continue
                    if not is_tech_role(basic["title"] or ""):
                        continue
                    location = basic["location"]
                    if search["remote"] and location and "remote" not in location.casefold():
                        location = f"{location} (Remote)"
                    elif search["remote"] and not location:
                        location = "Remote"
                    elif search["label"] == "India hybrid" and "hybrid" not in location.casefold():
                        location = f"{location} (Hybrid)" if location else "India (Hybrid)"
                    if not keeps_india_hybrid_or_remote(location):
                        print()
                        print(
                            "Skipped (not India, Indian hybrid, or remote): "
                            f"{basic['title']} — {basic['location']}"
                        )
                        continue
                    seen_urls.add(url)
                    new_jobs += 1

                    print()
                    print(f"[{len(jobs) + 1}]" if cap is None else f"[{len(jobs) + 1}/{cap}]")
                    print(f"Title    : {basic['title']}")
                    print(f"Company  : {basic['company']}")
                    print(f"Location : {location}")
                    if random_delay():
                        return
                    details = extract_job_details(url, basic["posted_at"])
                    if (
                        posted_within_days
                        and details["posted_at"]
                        and not within_days(details["posted_at"], posted_within_days)
                    ):
                        print("Skipped (outside the posted window).")
                        continue
                    print(f"Experience : {details['experience'] or 'not listed'}")
                    print(f"Skill      : {details['skill'] or 'not listed'}")
                    print(f"Salary     : {details['salary'] or 'not listed'}")
                    print(f"Added on   : {details['posted_at'] or 'not listed'}")
                    print(
                        "Description: "
                        f"{'collected' if details['job_description'] or details['about_company'] else 'not listed'}"
                    )
                    job = Job(
                        source=self.label,
                        title=basic["title"] or "",
                        company=basic["company"] or "",
                        location=location or "",
                        url=url,
                        posted_at=details["posted_at"] or "",
                        experience=details["experience"] or "",
                        skill=details["skill"] or "",
                        salary=details["salary"] or "",
                        about_company=details["about_company"] or "",
                        job_description=details["job_description"] or "",
                    )
                    jobs.append(job)
                    STORE.append(job, epoch)
                    if on_batch is not None:
                        on_batch([job])
                    print(f"Collected: {len(jobs)}" + (f"/{cap}" if cap else ""))

                if stale(started):
                    return
                if new_jobs == 0:
                    print("No new jobs found. Stopping.")
                    break
                start += page_size
                if (cap is None or len(jobs) < cap) and random_delay():
                    return


if __name__ == "__main__":
    print("=" * 70)
    print("LINKEDIN JOBS")
    print("Tech roles in India, Indian hybrid, and remote")
    print("=" * 70)
    try:
        LinkedIn().fetch(limit=0, open_browser=False)
    except KeyboardInterrupt:
        print("Stopped.")
