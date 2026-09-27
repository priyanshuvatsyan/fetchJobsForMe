"""Normalize Ashby job-board posts into the shared Job shape."""

from Server.api import (
    Job,
    clean,
    company_from_slug,
    extract_salary,
    fetch_ashby_board,
    job_matches,
    job_profile,
    load_boards,
    select_jobs,
    to_datetime,
)
from connectors.companies import COMPANIES


def _location(item: dict) -> str:
    parts = [clean(item.get("location"))]
    for extra in item.get("secondaryLocations") or []:
        if isinstance(extra, dict):
            parts.append(clean(extra.get("location") or extra.get("name")))
        else:
            parts.append(clean(extra))
    workplace = clean(item.get("workplaceType"))
    joined = ", ".join(part for part in parts if part)
    if workplace and workplace.casefold() not in joined.casefold():
        joined = ", ".join(part for part in (joined, workplace) if part)
    if item.get("isRemote") and "remote" not in joined.casefold():
        joined = ", ".join(part for part in (joined, "Remote") if part)
    return joined


class Ashby:
    key = "ashby"
    label = "Ashby"

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

        def accept(board: str, payload) -> bool:
            if not isinstance(payload, dict):
                return False
            company = company_from_slug(board)
            for item in payload.get("jobs") or []:
                if item.get("isListed") is False:
                    continue
                title = clean(item.get("title"))
                body = item.get("descriptionPlain") or item.get("descriptionHtml") or ""
                experience, skill = job_profile(title, body)
                jobs.append(
                    Job(
                        source=self.label,
                        title=title,
                        company=company,
                        location=_location(item),
                        url=clean(item.get("jobUrl") or item.get("applyUrl")),
                        posted_at=to_datetime(item.get("publishedAt")),
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
            fetch_ashby_board,
            workers=3,
            accept=accept,
        )
        del found
        return select_jobs(jobs, query, where, limit)
