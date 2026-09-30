"""Working Nomads' public exposed-jobs JSON feed."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, job_profile, plain_text, split_description, to_datetime
from Server.feeds import SidecarConnector

API_URL = "https://www.workingnomads.com/api/exposed_jobs/"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/json"}


class WorkingNomads(SidecarConnector):
    key = "workingnomads"
    label = "Working Nomads"

    def iter_items(self, query: str, posted_within_days: int | None):
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        for item in response.json():
            text = f"{item.get('title', '')} {item.get('company_name', '')} {item.get('tags', '')}"
            if not query or query.casefold() in text.casefold():
                yield item

    def parse_item(self, item: dict) -> Job:
        body = item.get("description") or ""
        about, description = split_description(body)
        tags = [part.strip() for part in clean(item.get("tags")).split(",") if part.strip()]
        title = clean(item.get("title"))
        return Job(
            source=self.label,
            title=title,
            company=clean(item.get("company_name")),
            location=f"{clean(item.get('location')) or 'Anywhere'} (Remote)",
            url=clean(item.get("url")),
            posted_at=to_datetime(item.get("pub_date")),
            experience=job_profile(title, body)[0],
            skill=format_skills(tags),
            about_company=about,
            job_description=description or plain_text(body),
        )
