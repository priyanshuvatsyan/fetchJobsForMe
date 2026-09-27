"""Normalize Lever postings into the shared Job shape."""

from Server.api import (
    Job,
    clean,
    company_from_slug,
    extract_salary,
    fetch_lever_postings,
    job_matches,
    job_profile,
    load_boards,
    select_jobs,
    to_datetime,
)
from connectors.companies import COMPANIES


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
    ) -> list[Job]:
        jobs: list[Job] = []
        companies_seen: set[str] = set()
        page = min(max(limit * 3, 8), 15)

        def accept(site: str, postings) -> bool:
            if not isinstance(postings, list):
                return False
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
                body = " ".join(
                    clean(item.get(key))
                    for key in ("descriptionPlain", "openingPlain")
                    if item.get(key)
                )
                experience, skill = job_profile(title, body)
                jobs.append(
                    Job(
                        source=self.label,
                        title=title,
                        company=company,
                        location=place,
                        url=clean(item.get("hostedUrl") or item.get("applyUrl")),
                        posted_at=to_datetime(item.get("createdAt")),
                        experience=experience,
                        skill=skill,
                        salary=extract_salary(body),
                    )
                )
                if not job_matches(jobs[-1], query, where):
                    jobs.pop()
            if any(job.company == company for job in jobs):
                companies_seen.add(company.casefold())
            return len(jobs) >= limit and len(companies_seen) >= min(3, limit)

        found, self.warnings = load_boards(
            boards or COMPANIES,
            lambda site: fetch_lever_postings(site, limit=page),
            workers=6,
            accept=accept,
        )
        del found
        return select_jobs(jobs, query, where, limit)
