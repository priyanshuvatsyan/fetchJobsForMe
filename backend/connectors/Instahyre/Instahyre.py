"""Instahyre's public India tech-job search feed."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills
from Server.control import cancelled, pause
from Server.feeds import SidecarConnector

API_URL = "https://www.instahyre.com/api/v1/job_search/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0.0.0",
    "Accept": "application/json",
}
TECH_FUNCTIONS = (10, 1, 9, 76)  # backend, full-stack, data/ML, other software
PAGE_SIZE = 35


class Instahyre(SidecarConnector):
    key = "instahyre"
    label = "Instahyre"

    def iter_items(self, query: str, posted_within_days: int | None):
        del posted_within_days
        for function_id in TECH_FUNCTIONS:
            if cancelled():
                return
            offset = 0
            while offset < 10_000:
                if cancelled():
                    return
                params = {
                    "job_functions": function_id,
                    "offset": offset,
                    "limit": PAGE_SIZE,
                }
                response = None
                for attempt in range(4):
                    response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
                    if response.status_code != 429:
                        break
                    if pause(15 * (attempt + 1)):
                        return
                assert response is not None
                response.raise_for_status()
                payload = response.json()
                items = payload.get("objects") or []
                if not items:
                    break
                for item in items:
                    text = (
                        f"{item.get('title', '')} "
                        f"{(item.get('employer') or {}).get('company_name', '')} "
                        f"{' '.join(item.get('keywords') or [])}"
                    )
                    if not query or query.casefold() in text.casefold():
                        yield item
                meta = payload.get("meta") or {}
                offset += int(meta.get("limit") or PAGE_SIZE)
                if not meta.get("next"):
                    break
                # The public endpoint starts throttling near 20 rapid requests.
                if pause(3.2):
                    return

    def parse_item(self, item: dict) -> Job:
        employer = item.get("employer") or {}
        title = clean(item.get("candidate_title") or item.get("title"))
        return Job(
            source=self.label,
            title=title,
            company=clean(employer.get("company_name")),
            location=clean(item.get("locations")) or "India",
            url=clean(item.get("public_url")),
            posted_at="",  # The public feed does not expose a reliable publication timestamp.
            skill=format_skills(item.get("keywords")),
            about_company=clean(employer.get("instahyre_note")),
            job_description="",
        )
