"""4 Day Week official public jobs API."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, job_profile, plain_text, split_description, to_datetime
from Server.feeds import SidecarConnector

API_URL = "https://4dayweek.io/api/v2/jobs"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/json"}


class FourDayWeek(SidecarConnector):
    key = "fourdayweek"
    label = "4 Day Week"

    def iter_items(self, query: str, posted_within_days: int | None):
        selected = tuple(getattr(self, "search_phrases", ()) or ())
        searches = selected or ((query,) if query else ("",))
        for search in searches:
            for page in range(1, 101):
                params = {
                    "page": page,
                    "limit": 100,
                    "posted_after": posted_within_days or 15,
                    "category": "engineering",
                    "sort": "date",
                }
                if search:
                    params["q"] = search
                try:
                    response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
                    response.raise_for_status()
                except requests.RequestException as exc:
                    self.warnings.append(f"4 Day Week skipped {search or 'the engineering feed'}: {exc}")
                    break
                payload = response.json()
                yield from payload.get("data") or []
                if not payload.get("has_more"):
                    break

    def parse_item(self, item: dict) -> Job:
        body = item.get("description") or ""
        about, description = split_description(body)
        locations = []
        for location in item.get("locations") or []:
            if not isinstance(location, dict):
                continue
            text = ", ".join(
                clean(location.get(key)) for key in ("city", "state", "country") if location.get(key)
            )
            if text and text not in locations:
                locations.append(text)
        arrangement = clean(item.get("work_arrangement"))
        location_text = "; ".join(locations) or arrangement or "Remote"
        if arrangement and arrangement.casefold() not in location_text.casefold():
            location_text += f" ({arrangement.title()})"
        skills = [
            value
            for group in ("skills", "stack", "tools")
            for value in (item.get(group) or [])
        ]
        low, high = item.get("salary_min"), item.get("salary_max")
        salary = ""
        if low or high:
            # The API documents salary integer values in cents.
            fmt = lambda value: f"{int(value) / 100:,.0f}" if value else ""  # noqa: E731
            salary = f"{clean(item.get('salary_currency')) or 'USD'} {fmt(low)}"
            if high and high != low:
                salary += f"–{fmt(high)}"
            salary += f"/{clean(item.get('salary_period')) or 'year'}"
        company = item.get("company") or {}
        return Job(
            source=self.label,
            title=clean(item.get("title")),
            company=clean(company.get("name")),
            location=location_text,
            url=clean(item.get("url")),
            posted_at=to_datetime(item.get("posted_at")),
            experience=clean(item.get("level")) or job_profile(item.get("title") or "", body)[0],
            skill=format_skills(skills),
            salary=salary,
            about_company=clean(company.get("short_description")) or about,
            job_description=description or plain_text(body),
        )
