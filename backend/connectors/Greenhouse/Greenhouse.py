"""Normalize Greenhouse board jobs into the shared Job shape."""

from dataclasses import replace

from concurrent.futures import ThreadPoolExecutor

from Server.api import (
    ApiError,
    Job,
    clean,
    extract_salary,
    format_skills,
    fetch_greenhouse_board,
    fetch_greenhouse_job,
    job_matches,
    job_profile,
    load_boards,
    select_jobs,
    to_datetime,
)
from connectors.companies import COMPANIES

_WORKPLACE = {"in-office", "hybrid", "remote", "distributed", "on-site", "onsite", "on site"}
_FIRST = ["discord", "cloudflare", "groww", "airbnb", "stripe", "databricks", "datadog"]


def _ordered_boards(boards: list[str] | None) -> list[str]:
    tokens = list(boards or COMPANIES)
    if boards:
        return tokens
    front = [token for token in _FIRST if token in set(tokens)]
    return front + [token for token in tokens if token not in front]


def _location(item: dict) -> str:
    location = item.get("location") or {}
    name = clean(location.get("name") if isinstance(location, dict) else location)
    places: list[str] = []
    for field in item.get("metadata") or []:
        if not isinstance(field, dict) or "location" not in clean(field.get("name")).casefold():
            continue
        value = field.get("value")
        if isinstance(value, list):
            places.extend(clean(part) for part in value if clean(part))
        elif clean(value):
            places.append(clean(value))
    if places and (not name or name.casefold() in _WORKPLACE):
        return ", ".join(dict.fromkeys(places))
    return name


def _salary_from_metadata(item: dict) -> str:
    for field in item.get("metadata") or []:
        if not isinstance(field, dict):
            continue
        name = clean(field.get("name")).casefold()
        if not any(word in name for word in ("salary", "compensation", "pay range", "pay")):
            continue
        value = field.get("value")
        if isinstance(value, list):
            text = ", ".join(clean(part) for part in value if clean(part))
        else:
            text = clean(value)
        if text:
            return text
    return ""


def _skills_from_metadata(item: dict) -> str:
    values = []
    for field in item.get("metadata") or []:
        if not isinstance(field, dict):
            continue
        if "skill" not in clean(field.get("name")).casefold():
            continue
        value = field.get("value")
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.append(value)
    return format_skills(values)


class Greenhouse:
    key = "greenhouse"
    label = "Greenhouse"

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 10,
        boards: list[str] | None = None,
    ) -> list[Job]:
        jobs: list[Job] = []
        details: dict[str, tuple[str, object]] = {}
        company_count = 0
        companies_seen: set[str] = set()

        def accept(board: str, payload) -> bool:
            nonlocal company_count
            if not isinstance(payload, dict):
                return False
            for item in payload.get("jobs") or []:
                url = clean(item.get("absolute_url"))
                title = clean(item.get("title"))
                company = clean(item.get("company_name")) or board
                job = Job(
                    source=self.label,
                    title=title,
                    company=company,
                    location=_location(item),
                    url=url,
                    posted_at=to_datetime(item.get("first_published") or item.get("updated_at")),
                    salary=_salary_from_metadata(item),
                    skill=_skills_from_metadata(item),
                )
                if not job.title or not job.url or not job_matches(job, query, where):
                    continue
                jobs.append(job)
                details[url] = (board, item.get("id"))
                key = company.casefold()
                if key not in companies_seen:
                    companies_seen.add(key)
                    company_count += 1
            return len(jobs) >= limit and company_count >= min(4, limit)

        found, self.warnings = load_boards(
            _ordered_boards(boards),
            fetch_greenhouse_board,
            workers=12,
            accept=accept,
        )
        del found
        selected = select_jobs(jobs, query, where, limit)
        if not selected:
            return []
        with ThreadPoolExecutor(max_workers=min(6, len(selected))) as pool:
            return list(pool.map(lambda job: self._enrich(job, details), selected))

    def _enrich(self, job: Job, details: dict[str, tuple[str, object]]) -> Job:
        board, job_id = details.get(job.url, ("", None))
        body = ""
        detail: dict = {}
        if board and job_id is not None:
            try:
                detail = fetch_greenhouse_job(board, job_id)
                body = detail.get("content") or ""
            except (ApiError, ValueError, OSError) as exc:
                self.warnings.append(f"{board}/{job_id}: {exc}")
        experience, _skill = job_profile(job.title, body)
        listed = _skills_from_metadata(detail) if isinstance(detail, dict) else ""
        return replace(
            job,
            experience=experience,
            skill=listed or job.skill,
            salary=extract_salary(body, job.salary),
        )
