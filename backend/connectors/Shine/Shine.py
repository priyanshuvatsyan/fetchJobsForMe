"""Shine's public India jobs JSON search feed."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, plain_text, split_description, to_datetime, within_days
from Server.feeds import SidecarConnector

API_URL = "https://www.shine.com/api/v2/search/simple/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0.0.0",
    "Accept": "application/json",
    "Referer": "https://www.shine.com/",
}
TECH_QUERIES = (
    "software engineer",
    "software developer",
    "data engineer",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "devops engineer",
    "cloud engineer",
    "cybersecurity",
    "QA automation",
)


def shine_time(value) -> str:
    text = clean(value)
    if not text:
        return ""
    if text.endswith("Z") or "+" in text[10:] or "-" in text[10:]:
        return to_datetime(text)
    return to_datetime(f"{text}+05:30")


class Shine(SidecarConnector):
    key = "shine"
    label = "Shine"

    def iter_items(self, query: str, posted_within_days: int | None):
        searches = (query,) if query else TECH_QUERIES
        for search in searches:
            for page in range(1, 101):
                response = requests.get(
                    API_URL,
                    params={"q": search, "page": page},
                    headers=HEADERS,
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                items = payload.get("results") or []
                if not items:
                    break
                for item in items:
                    yield item
                dated = [shine_time(item.get("jPDate")) for item in items]
                dated = [stamp for stamp in dated if stamp]
                if posted_within_days and dated and all(
                    not within_days(stamp, posted_within_days) for stamp in dated
                ):
                    break
                if page >= int(payload.get("num_pages") or page):
                    break

    def parse_item(self, item: dict) -> Job:
        body = item.get("jJD") or item.get("jJDT") or ""
        about, description = split_description(body)
        slug = clean(item.get("jSlug"))
        skills = [part.strip() for part in clean(item.get("jKwd")).split(",") if part.strip()]
        salary = clean(item.get("jSal"))
        location = ", ".join(clean(value) for value in (item.get("jLoc") or []) if clean(value))
        return Job(
            source=self.label,
            title=clean(item.get("jJT")),
            company=clean(item.get("jCName")),
            location=location or "India",
            url=f"https://www.shine.com/jobs/{slug.strip('/')}/" if slug else "",
            posted_at=shine_time(item.get("jPDate")),
            experience=clean(item.get("jExp")),
            skill=format_skills(skills),
            salary=salary,
            about_company=about,
            job_description=description or plain_text(body),
        )
