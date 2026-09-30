"""The Muse official public jobs API."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, job_profile, plain_text, split_description, to_datetime
from Server.control import cancelled
from Server.feeds import SidecarConnector

API_URL = "https://www.themuse.com/api/public/jobs"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/json"}
TECH_CATEGORIES = ("Software Engineering", "Data Science", "IT")


class TheMuse(SidecarConnector):
    key = "themuse"
    label = "The Muse"

    def iter_items(self, query: str, posted_within_days: int | None):
        for category in TECH_CATEGORIES:
            if cancelled():
                return
            for page in range(1, 51):
                if cancelled():
                    return
                params = {"page": page, "descending": "true", "category": category}
                response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
                response.raise_for_status()
                payload = response.json()
                items = payload.get("results") or []
                if not items:
                    break
                for item in items:
                    if not query or query.casefold() in (
                        f"{item.get('name', '')} {(item.get('company') or {}).get('name', '')}".casefold()
                    ):
                        yield item
                if page >= int(payload.get("page_count") or page):
                    break

    def parse_item(self, item: dict) -> Job:
        body = item.get("contents") or ""
        about, description = split_description(body)
        return Job(
            source=self.label,
            title=clean(item.get("name")),
            company=clean((item.get("company") or {}).get("name")),
            location=", ".join(
                clean(location.get("name"))
                for location in (item.get("locations") or [])
                if isinstance(location, dict) and location.get("name")
            ),
            url=clean((item.get("refs") or {}).get("landing_page")),
            posted_at=to_datetime(item.get("publication_date")),
            experience=format_skills(item.get("levels"))
            or job_profile(item.get("name") or "", body)[0],
            skill=format_skills([*(item.get("categories") or []), *(item.get("tags") or [])]),
            about_company=about,
            job_description=description or plain_text(body),
        )
