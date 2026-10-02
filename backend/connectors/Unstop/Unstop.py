"""Public Unstop jobs API for tech roles in India, including remote and hybrid."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from Server.api import (
    Job,
    clean,
    format_skills,
    is_tech_role,
    keeps_india_hybrid_or_remote,
    job_profile,
    plain_text,
    split_description,
    to_datetime,
    within_days,
)
from Server.control import pause, stale, token
from Server.feeds import _matches_saved_search, get_store, search_phrases

API_URL = "https://unstop.com/api/public/opportunity/search-result"
STORE = get_store("unstop")
JOBS_FILE = STORE.path
PAGE_SIZE = 50
MAX_PAGES = 40

_CURRENCY = {
    "fa-rupee": "₹",
    "fa-dollar": "$",
    "fa-usd": "$",
    "fa-euro": "€",
    "fa-pound": "£",
}
_PAY = {"monthly": "/month", "annually": "/year", "yearly": "/year", "weekly": "/week"}
_WORKPLACE = {
    "wfh": "Remote",
    "remote": "Remote",
    "work_from_home": "Remote",
    "hybrid": "Hybrid",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://unstop.com/",
}

def posted_stamp(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stamped = to_datetime(text)
    if stamped:
        return stamped
    for pattern in ("%Y-%m-%d %H:%M:%S GMT%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            moment = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def job_posted_at(item: dict) -> str:
    registration = item.get("regnRequirements") or {}
    for value in (
        item.get("approved_date"),
        registration.get("start_regn_dt"),
        item.get("updated_at"),
    ):
        stamped = posted_stamp(value)
        if stamped:
            return stamped
    return ""


def workplace_label(item: dict) -> str:
    detail = item.get("jobDetail") or {}
    raw = str(detail.get("type") or "").strip().casefold()
    if not raw:
        registration = item.get("regnRequirements") or {}
        raw = str(registration.get("work_location_type") or "").strip().casefold()
    return _WORKPLACE.get(raw, "")


def keep_location(item: dict) -> bool:
    """India, Indian hybrid, or remote work."""
    text = location_text(item)
    countries = [
        str(loc.get("country"))
        for loc in (item.get("locations") or [])
        if isinstance(loc, dict) and loc.get("country")
    ]
    if any(country.casefold() == "india" for country in countries):
        return True
    if not countries and text in {"", "India"}:
        return True
    return keeps_india_hybrid_or_remote(text)


def location_text(item: dict) -> str:
    names: list[str] = []
    for loc in item.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        city = clean(loc.get("city") or loc.get("state") or "")
        if city and city not in names:
            names.append(city)
    if not names:
        for name in (item.get("jobDetail") or {}).get("locations") or []:
            city = clean(name)
            if city and city not in names:
                names.append(city)
    text = ", ".join(names)
    label = workplace_label(item)
    if label and label.casefold() not in text.casefold():
        text = f"{text} ({label})" if text else label
    return text or "India"


def salary_text(detail: dict) -> str:
    if not detail or detail.get("not_disclosed") or not detail.get("show_salary"):
        return ""
    symbol = _CURRENCY.get(detail.get("currency") or "", "")
    period = _PAY.get(str(detail.get("pay_in") or ""), "")

    def money(value) -> str:
        if value in (None, "", 0):
            return ""
        try:
            return f"{symbol}{int(value):,}"
        except (TypeError, ValueError):
            return ""

    low, high = money(detail.get("min_salary")), money(detail.get("max_salary"))
    if low and high and low != high:
        return f"{low}–{high}{period}"
    return f"{high or low}{period}" if (high or low) else ""


def experience_text(detail: dict, title: str, body: str) -> str:
    def years(value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    low, high = years(detail.get("min_experience")), years(detail.get("max_experience"))
    if low is not None and high is not None and low != high:
        return f"{low}-{high} years"
    if low is not None:
        return f"{low}+ years"
    if high is not None:
        return f"up to {high} years"
    return job_profile(title, body)[0]


def job_url(item: dict) -> str:
    seo = clean(item.get("seo_url"))
    if seo.startswith("http"):
        return seo
    public = clean(item.get("public_url"))
    if public:
        return "https://unstop.com/" + public.lstrip("/")
    if item.get("id"):
        return f"https://unstop.com/jobs/{item['id']}"
    return ""


def search_page(page: int, query: str) -> dict:
    params = {
        "opportunity": "jobs",
        "oppstatus": "open",
        "page": page,
        "per_page": PAGE_SIZE,
    }
    if query:
        params["searchTerm"] = query
    response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


class Unstop:
    key = "unstop"
    label = "Unstop"
    persist = "sidecar"

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 0,
        boards: list[str] | None = None,
        on_batch=None,
        posted_within_days: int | None = None,
        max_experience: int | None = None,
        role_terms: list[str] | None = None,
    ) -> list[Job]:
        del boards
        self.warnings = []
        self.max_experience = max_experience
        self.role_terms = [str(role).strip() for role in (role_terms or []) if str(role).strip()]
        self.search_phrases = search_phrases(self.role_terms)
        cap = None if limit <= 0 else limit
        place = where.strip().casefold()
        jobs: list[Job] = []
        seen: set[str] = set()
        started = token()
        epoch = STORE.reset()

        searches = self.search_phrases or [query.strip()]
        for search in searches:
            self._pages(
                search, place, jobs, seen, started, epoch, cap, posted_within_days, on_batch,
            )

        print()
        if STORE.epoch == epoch:
            STORE.flush()
        print(f"Saved {len(jobs)} jobs")
        print(f"File: {JOBS_FILE}")
        return jobs

    def _pages(
        self,
        query: str,
        place: str,
        jobs: list[Job],
        seen: set[str],
        started: int,
        epoch: int,
        cap: int | None,
        posted_within_days: int | None,
        on_batch,
    ) -> None:
        for page in range(1, MAX_PAGES + 1):
            if stale(started) or (cap is not None and len(jobs) >= cap):
                break
            print()
            print("=" * 70)
            print(f"UNSTOP PAGE   : {page}")
            print(f"JOBS COLLECTED: {len(jobs)}")
            print("=" * 70)
            try:
                data = search_page(page, query.strip())
            except requests.RequestException as error:
                print(f"Search request failed: {error}. Retrying.")
                if pause(1):
                    break
                try:
                    data = search_page(page, query.strip())
                except requests.RequestException as retry_error:
                    self.warnings.append(f"Unstop search failed: {retry_error}")
                    print(f"Search request failed: {retry_error}")
                    break

            items = data.get("data") or []
            if not items:
                print("No more jobs.")
                break

            for item in items:
                if stale(started):
                    break
                if not isinstance(item, dict):
                    continue
                if cap is not None and len(jobs) >= cap:
                    break
                try:
                    url = job_url(item)
                    title = clean(item.get("title"))
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    posted = job_posted_at(item)
                    if not is_tech_role(title):
                        continue
                    if not keep_location(item):
                        continue
                    if posted and posted_within_days and not within_days(posted, posted_within_days):
                        continue
                    location = location_text(item)
                    if place and place not in f"{title} {location}".casefold():
                        continue

                    detail = item.get("jobDetail") or {}
                    body = plain_text(item.get("details") or "")
                    about_company, job_description = split_description(body)
                    organisation = item.get("organisation") or {}
                    skill = format_skills(item.get("required_skills"))
                    if not skill:
                        skill = job_profile(title, body)[1]
                    job = Job(
                        source=self.label,
                        title=title,
                        company=clean(organisation.get("name")),
                        location=location,
                        url=url,
                        posted_at=posted,
                        experience=experience_text(detail, title, body),
                        skill=skill,
                        salary=salary_text(detail),
                        about_company=about_company,
                        job_description=job_description or body,
                    )
                except (TypeError, ValueError) as error:
                    print(f"Skipped a listing: {error}")
                    continue
                if not _matches_saved_search(
                    job,
                    getattr(self, "max_experience", None),
                    getattr(self, "role_terms", None) or [],
                ):
                    continue
                jobs.append(job)
                STORE.append(job, epoch)
                if on_batch is not None:
                    on_batch([job])
                print(f"[{len(jobs)}] {title} — {job.company} — {location}")

            # Newest posts are mixed through later pages, so keep reading the feed.
            last_page = int(data.get("last_page") or page)
            if page >= last_page:
                break


if __name__ == "__main__":
    print("=" * 70)
    print("UNSTOP JOBS")
    print("Tech roles in India, remote, and hybrid")
    print("=" * 70)
    try:
        Unstop().fetch(limit=0, posted_within_days=30)
    except KeyboardInterrupt:
        print("Stopped.")
