"""Jobicy official public remote-jobs API."""

from __future__ import annotations

import requests

from Server.api import Job, clean, format_skills, job_profile, plain_text, split_description, to_datetime
from Server.feeds import SidecarConnector, search_phrases

API_URL = "https://jobicy.com/api/v2/remote-jobs"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/json"}
# Jobicy rejects unknown tags such as "ML". These are tags the API accepts.
_JOBICY_TAGS = {
    "ml": "machine-learning",
    "machine learning": "machine-learning",
    "ml engineer": "machine-learning",
    "mlops": "machine-learning",
    "ai": "data-science",
    "artificial intelligence": "data-science",
    "ai engineer": "data-science",
    "generative ai": "data-science",
    "data": "data-science",
    "data science": "data-science",
    "data scientist": "data-science",
    "data analyst": "data",
    "data engineer": "data",
    "devops": "devops",
    "dev ops": "devops",
    "sre": "devops",
    "site reliability": "devops",
    "developer": "software-development",
    "software developer": "software-development",
    "software engineer": "software-development",
    "qa": "software-development",
    "quality assurance": "software-development",
    "qa engineer": "software-development",
    "testing": "software-development",
    "frontend": "frontend",
    "frontend developer": "frontend",
    "backend": "backend",
    "backend developer": "backend",
}


def jobicy_tags(roles: list[str] | None) -> list[str]:
    """Turn saved roles into Jobicy tags. ML becomes machine-learning, never the raw code."""
    tags: list[str] = []
    for phrase in search_phrases(roles):
        tag = _JOBICY_TAGS.get(phrase.casefold())
        if tag and tag not in tags:
            tags.append(tag)
    return tags


class Jobicy(SidecarConnector):
    key = "jobicy"
    label = "Jobicy"

    def iter_items(self, query: str, posted_within_days: int | None):
        del posted_within_days
        tags = jobicy_tags(getattr(self, "role_terms", None))
        if query.strip() and not tags:
            tags = jobicy_tags([query])
        # No tag means the general feed. Saved roles are still filtered after parsing.
        for tag in tags or [""]:
            params = {"count": 50}
            if tag:
                params["tag"] = tag
            try:
                response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            except requests.RequestException as exc:
                self.warnings.append(f"Jobicy skipped {tag or 'the general feed'}: {exc}")
                continue
            if response.status_code == 400:
                self.warnings.append(f"Jobicy skipped unsupported tag {tag or 'general'}")
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                self.warnings.append(f"Jobicy skipped {tag or 'the general feed'}: {exc}")
                continue
            yield from payload.get("jobs") or []

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
