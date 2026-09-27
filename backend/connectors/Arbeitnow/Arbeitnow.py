"""Normalize Arbeitnow listings into the shared Job shape."""

from Server.api import ApiError, Job, clean, extract_salary, fetch_arbeitnow_jobs, job_profile, select_jobs, to_datetime


class Arbeitnow:
    key = "arbeitnow"
    label = "Arbeitnow"

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
        try:
            payload = fetch_arbeitnow_jobs()
        except ApiError as exc:
            self.warnings.append(str(exc))
            return []
        jobs = []
        for item in payload.get("data") or []:
            location = clean(item.get("location"))
            if item.get("remote") and "remote" not in location.casefold():
                location = ", ".join(part for part in (location, "Remote") if part)
            url = clean(item.get("url"))
            if url.startswith("/"):
                url = f"https://www.arbeitnow.com{url}"
            title = clean(item.get("title"))
            body = item.get("description") or ""
            experience, skill = job_profile(title, body, item.get("tags"))
            jobs.append(
                Job(
                    source=self.label,
                    title=title,
                    company=clean(item.get("company_name")),
                    location=location,
                    url=url,
                    posted_at=to_datetime(item.get("created_at")),
                    experience=experience,
                    skill=skill,
                    salary=extract_salary(body),
                )
            )
        return select_jobs(jobs, query, where, limit)
