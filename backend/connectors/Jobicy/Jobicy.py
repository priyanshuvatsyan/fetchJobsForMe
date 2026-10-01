"""Jobicy official public remote-jobs API."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, job_profile, plain_text, split_description, to_datetime
from Server.feeds import SidecarConnector

API_URL = "https://jobicy.com/api/v2/remote-jobs"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/json"}


class Jobicy(SidecarConnector):
    key = "jobicy"
    label = "Jobicy"

    def iter_items(self, query: str, posted_within_days: int | None):
        params = {"count": 100}
        if query:
            params["tag"] = query
        response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        yield from response.json().get("jobs") or []

    def parse_item(self, item: dict) -> Job:
        body = item.get("jobDescription") or ""
        about, description = split_description(body)
        low, high = item.get("salaryMin"), item.get("salaryMax")
        salary = ""
        if low or high:
            currency = clean(item.get("salaryCurrency")) or "USD"
            values = f"{int(low):,}" if low else ""
            if high and high != low:
                values += f"–{int(high):,}"
            salary = f"{currency} {values}/{clean(item.get('salaryPeriod')) or 'year'}"
        tags = item.get("jobIndustry") or []
        return Job(
            source=self.label,
            title=clean(item.get("jobTitle")),
            company=clean(item.get("companyName")),
            location=f"{clean(item.get('jobGeo')) or 'Anywhere'} (Remote)",
            url=clean(item.get("url")),
            posted_at=to_datetime(item.get("pubDate")),
            experience=clean(item.get("jobLevel")) or job_profile(item.get("jobTitle") or "", body)[0],
            skill=format_skills(tags),
            salary=salary,
            about_company=about,
            job_description=description or plain_text(body),
        )
