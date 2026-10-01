"""Normalize RemoteOK listings into the shared Job shape."""

from Server.api import ApiError, Job, clean, extract_salary, fetch_remoteok_jobs, job_profile, money_span, select_jobs, split_description, to_datetime


class RemoteOK:
    key = "remoteok"
    label = "RemoteOK"

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
            payload = fetch_remoteok_jobs()
        except (ApiError, ValueError) as exc:
            self.warnings.append(str(exc))
            return []
        jobs = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            title = clean(item.get("position"))
            body = item.get("description") or ""
            experience, skill = job_profile(title, body, item.get("tags"))
            about_company, job_description = split_description(body)
            place = clean(item.get("location")) or "Remote"
            if "remote" not in place.casefold():
                place = f"{place} (Remote)"
            jobs.append(
                Job(
                    source=self.label,
                    title=title,
                    company=clean(item.get("company")),
                    location=place,
                    url=clean(item.get("url") or item.get("apply_url")),
                    posted_at=to_datetime(item.get("epoch") or item.get("date")),
                    experience=experience,
                    skill=skill,
                    salary=money_span(item.get("salary_min"), item.get("salary_max")) or extract_salary(body),
                    about_company=about_company,
                    job_description=job_description,
                )
            )
        return select_jobs(jobs, query, where, limit)
