"""Normalize Remotive remote jobs into the shared Job shape."""

from Server.api import ApiError, Job, clean, extract_salary, fetch_remotive_jobs, job_profile, select_jobs, split_description, to_datetime


class Remotive:
    key = "remotive"
    label = "Remotive"

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 10,
        boards: list[str] | None = None,
    ) -> list[Job]:
        del boards
        self.warnings = []
        page_size = 0 if limit <= 0 else min(max(limit * 5, limit), 50)
        try:
            payload = fetch_remotive_jobs(query, limit=page_size)
        except ApiError as exc:
            self.warnings.append(str(exc))
            return []
        jobs = []
        for item in payload.get("jobs") or []:
            title = clean(item.get("title"))
            body = item.get("description") or ""
            experience, skill = job_profile(title, body, item.get("tags"))
            about_company, job_description = split_description(body)
            jobs.append(
                Job(
                    source=self.label,
                    title=title,
                    company=clean(item.get("company_name")),
                    location=clean(item.get("candidate_required_location")),
                    url=clean(item.get("url")),
                    posted_at=to_datetime(item.get("publication_date")),
                    experience=experience,
                    skill=skill,
                    salary=extract_salary(body, item.get("salary") or ""),
                    about_company=about_company,
                    job_description=job_description,
                )
            )
        return select_jobs(jobs, query, where, limit)
