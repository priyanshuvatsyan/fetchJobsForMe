"""Normalize Adzuna search results into the shared Job shape."""

from Server.api import (
    ApiError,
    Job,
    adzuna_credentials,
    clean,
    fetch_adzuna_jobs,
    job_profile,
    money_span,
    select_jobs,
    to_datetime,
)


class Adzuna:
    key = "adzuna"
    label = "Adzuna"

    def __init__(self, country: str = "in") -> None:
        self.country = country or "in"
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
        if len(self.country) != 2 or not self.country.isalpha():
            self.warnings.append("country must be a 2-letter code such as in or gb")
            return []
        self.country = self.country.lower()
        if not all(adzuna_credentials()):
            self.warnings.append(
                "skipped — set ADZUNA_APP_ID and ADZUNA_APP_KEY (free key at developer.adzuna.com)"
            )
            return []
        try:
            payload = fetch_adzuna_jobs(self.country, query, where, limit)
        except (ApiError, ValueError) as exc:
            self.warnings.append(str(exc))
            return []
        jobs = []
        for item in payload.get("results") or []:
            company = item.get("company") or {}
            location = item.get("location") or {}
            title = clean(item.get("title"))
            body = item.get("description") or ""
            experience, skill = job_profile(title, body)
            currency = clean(item.get("salary_currency") or "USD")
            symbol = {"USD": "$", "GBP": "£", "EUR": "€", "INR": "₹", "CAD": "$", "AUD": "$"}.get(currency, f"{currency} ")
            jobs.append(
                Job(
                    source=self.label,
                    title=title,
                    company=clean(company.get("display_name") if isinstance(company, dict) else company),
                    location=clean(location.get("display_name") if isinstance(location, dict) else location),
                    url=clean(item.get("redirect_url")),
                    posted_at=to_datetime(item.get("created")),
                    experience=experience,
                    skill=skill,
                    salary=money_span(item.get("salary_min"), item.get("salary_max"), symbol),
                )
            )
        return select_jobs(jobs, "", "", limit)
