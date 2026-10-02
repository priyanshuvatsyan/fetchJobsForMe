"""Normalize Lever postings into the shared Job shape."""

from Server.api import (
    Job,
    clean,
    company_from_slug,
    extract_salary,
    fetch_lever_postings,
    job_matches,
    keeps_india_hybrid_or_remote,
    job_profile,
    load_boards,
    split_description,
    select_jobs,
    to_datetime,
    within_days,
)
from connectors.companies import COMPANIES

# These sites are on Lever. Asking them first avoids hundreds of misses on other portals.
_FIRST = [
    "spotify",
    "palantir",
    "netflix",
    "atlassian",
    "eventbrite",
    "100ms",
    "allegiantair",
    "blablacar",
    "cartrawler",
    "kpmg",
]


def _ordered_sites(boards: list[str] | None) -> list[str]:
    tokens = list(boards or COMPANIES)
    if boards:
        return tokens
    front = [token for token in _FIRST if token in set(tokens)]
    return front + [token for token in tokens if token not in front]


class Lever:
    key = "lever"
    label = "Lever"

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 10,
        boards: list[str] | None = None,
        posted_within_days: int | None = None,
        on_batch=None,
    ) -> list[Job]:
        jobs: list[Job] = []
        companies_seen: set[str] = set()
        page = 0 if limit <= 0 else min(max(limit * 3, 8), 15)

        def accept(site: str, postings) -> bool:
            if not isinstance(postings, list):
                return False
            start = len(jobs)
            company = company_from_slug(site)
            for item in postings:
                categories = item.get("categories") or {}
                locations = categories.get("allLocations") or []
                if not locations and categories.get("location"):
                    locations = [categories["location"]]
                place = ", ".join(clean(name) for name in locations if clean(name))
                workplace = clean(item.get("workplaceType"))
                if workplace and workplace.casefold() not in place.casefold():
                    place = ", ".join(part for part in (place, workplace) if part)
                title = clean(item.get("text"))
                body = "\n\n".join(
                    item.get(key) or ""
                    for key in ("descriptionPlain", "openingPlain")
                    if item.get(key)
                )
                sections = []
                for section in item.get("lists") or []:
                    heading = clean(section.get("text"))
                    content = section.get("content") or ""
                    sections.append(f"{heading}\n{content}" if heading else content)
                posted_at = to_datetime(item.get("createdAt"))
                if posted_within_days and not within_days(posted_at, posted_within_days):
                    continue
                experience, skill = job_profile(title, body)
                about_company, job_description = split_description(body, *sections)
                jobs.append(
                    Job(
                        source=self.label,
                        title=title,
                        company=company,
                        location=place,
                        url=clean(item.get("hostedUrl") or item.get("applyUrl")),
                        apply_url=clean(item.get("applyUrl")),
                        posted_at=posted_at,
                        experience=experience,
                        skill=skill,
                        salary=extract_salary(body),
                        about_company=about_company,
                        job_description=job_description,
                    )
                )
                if not job_matches(jobs[-1], query, where) or not keeps_india_hybrid_or_remote(
                    jobs[-1].location
                ):
                    jobs.pop()
            if on_batch is not None and len(jobs) > start:
                on_batch(jobs[start:])
            if any(job.company == company for job in jobs):
                companies_seen.add(company.casefold())
            if limit <= 0:
                return False
            return len(jobs) >= limit and len(companies_seen) >= min(3, limit)

        found, self.warnings = load_boards(
            _ordered_sites(boards),
            lambda site: fetch_lever_postings(site, limit=page),
            workers=8,
            accept=accept,
        )
        del found
        return select_jobs(jobs, query, where, limit)
