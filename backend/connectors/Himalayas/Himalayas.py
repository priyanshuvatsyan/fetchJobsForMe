"""Himalayas official public remote-jobs API."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, job_profile, plain_text, split_description, to_datetime
from Server.feeds import SidecarConnector

API_URL = "https://himalayas.app/jobs/api"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/json"}


class Himalayas(SidecarConnector):
    key = "himalayas"
    label = "Himalayas"

    def iter_items(self, query: str, posted_within_days: int | None):
        cursor = ""
        for _ in range(100):
            params = {"limit": 20}
            if cursor:
                params["cursor"] = cursor
            response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            payload = response.json()
            items = payload.get("jobs") or []
            if not items:
                break
            for item in items:
                if not query or query.casefold() in (
                    f"{item.get('title', '')} {item.get('companyName', '')}".casefold()
                ):
                    yield item
            cursor = payload.get("nextCursor") or ""
            if not cursor:
                break

    def parse_item(self, item: dict) -> Job:
        body = item.get("description") or ""
        about, description = split_description(body)
        salary = ""
        low, high = item.get("minSalary"), item.get("maxSalary")
        if low or high:
            currency = clean(item.get("currency")) or "USD"
            amount = lambda value: f"{int(value):,}" if value not in (None, "") else ""  # noqa: E731
            salary = f"{currency} {amount(low)}"
            if high and high != low:
                salary += f"–{amount(high)}"
            salary += f"/{clean(item.get('salaryPeriod')) or 'year'}"
        location = ", ".join(item.get("locationRestrictions") or []) or "Remote"
        experience = ", ".join(item.get("seniority") or [])
        return Job(
            source=self.label,
            title=clean(item.get("title")),
            company=clean(item.get("companyName")),
            location=f"{location} (Remote)" if "remote" not in location.casefold() else location,
            url=clean(item.get("applicationLink") or item.get("guid")),
            posted_at=to_datetime(item.get("pubDate")),
            experience=experience or job_profile(item.get("title") or "", body)[0],
            skill=format_skills(item.get("categories")),
            salary=salary,
            about_company=about,
            job_description=description or plain_text(body),
        )
