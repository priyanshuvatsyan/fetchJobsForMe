"""Connect to public job APIs and print openings in the terminal.

Examples (from the project root):
  python backend/Server/server.py --query engineer --where Bengaluru
  python backend/Server/server.py --source linkedin --query python --where Bengaluru
  python backend/Server/server.py --source greenhouse --boards groww --limit 5
  python backend/Server/server.py                    (start the jobs API for the web app)
"""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import logging
import re
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree
import os
from firebase import get_firestore_client


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from Server.gemini_service import get_user_gemini_client

_LOGGER = logging.getLogger("fetchjobs")
_LOG_ENABLED = False


def enable() -> None:
    """Send INFO, WARNING, and ERROR lines to stdout. Safe to call twice.

    Stays off for the terminal CLI so printed JSON is unchanged. A line looks like:
    2026-10-01 02:20:01 INFO [fourdayweek] start window=15
    """
    global _LOG_ENABLED
    _LOG_ENABLED = True
    if _LOGGER.handlers:
        return
    _LOGGER.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _LOGGER.addHandler(handler)
    _LOGGER.propagate = False


def event(portal: str, level: str, message: str) -> None:
    """Log one portal lifecycle line. No-op until enable() runs."""
    if not _LOG_ENABLED:
        return
    numeric = getattr(logging, (level or "info").upper(), logging.INFO)
    _LOGGER.log(numeric, "[%s] %s", portal or "-", message)


from Server.api import (
    POSTED_WINDOW_DAYS,
    Job,
    apply_posting_facts,
    clean,
    is_tech_role,
    keeps_india_hybrid_or_remote,
    within_days,
)
from Server.control import arm, cancel, held
from Server.feeds import FeedCoordinator
from connectors.Adzuna import Adzuna
from connectors.Arbeitnow import Arbeitnow
from connectors.Ashby import Ashby
from connectors.Greenhouse import Greenhouse
from connectors.Lever import Lever
from connectors.RemoteOK import RemoteOK
from connectors.Remotive import Remotive
from connectors.LinkedIn import LinkedIn
from connectors.Unstop import Unstop
from connectors.FourDayWeek import FourDayWeek
from connectors.Himalayas import Himalayas
from connectors.Instahyre import Instahyre
from connectors.Jobicy import Jobicy
from connectors.Indeed import Indeed
from connectors.Naukri import Naukri
from connectors.Shine import Shine
from connectors.TheMuse import TheMuse
from connectors.WeWorkRemotely import WeWorkRemotely
from connectors.WorkingNomads import WorkingNomads

SLUG_SOURCES = {"greenhouse", "lever", "ashby"}
PAUSED_SIDECAR_KEYS = {"instahyre"}
CONNECTORS = [
    Greenhouse,
    Lever,
    Ashby,
    Remotive,
    RemoteOK,
    Arbeitnow,
    Adzuna,
    LinkedIn,
    Unstop,
    Shine,
    Indeed,
    Naukri,
    Instahyre,
    Himalayas,
    Jobicy,
    TheMuse,
    WorkingNomads,
    FourDayWeek,
    WeWorkRemotely,
]
BY_KEY = {connector.key: connector for connector in CONNECTORS}

WINDOW_DAYS = POSTED_WINDOW_DAYS
JOBS_FILE = Path(__file__).resolve().parents[1] / "data" / "jobs.json"
_jobs_lock = threading.Lock()
_progress = {
    "running": False,
    "generation": 0,
    "jobs": [],
    "index": {},
    "notes": [],
    "note_keys": set(),
    "credits": [],
    "error": "",
    "fetchedAt": "",
    "last_write": 0.0,
    "stopped": False,
}

CREDITS = {
    "remotive": "Credit: jobs from Remotive — https://remotive.com",
    "remoteok": "Credit: jobs from Remote OK — https://remoteok.com (link each job URL)",
    "adzuna": "Credit: Jobs by Adzuna — https://www.adzuna.com",
    "himalayas": "Jobs sourced from Himalayas — https://himalayas.app",
    "jobicy": "Jobs sourced from Jobicy — https://jobicy.com",
    "themuse": "Jobs sourced from The Muse — https://www.themuse.com",
    "fourdayweek": "Jobs sourced from 4 Day Week — https://4dayweek.io",
    "weworkremotely": "Jobs sourced from We Work Remotely — https://weworkremotely.com",
    "indeed": "Jobs sourced from Indeed — https://in.indeed.com",
    "naukri": "Jobs sourced from Naukri — https://www.naukri.com",
}
SIDECAR_SOURCES = [cls for cls in CONNECTORS if getattr(cls, "persist", "") == "sidecar"]
FEED_COORDINATOR = FeedCoordinator(SIDECAR_SOURCES, WINDOW_DAYS, paused=PAUSED_SIDECAR_KEYS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch jobs from public, legal APIs and print them.")
    parser.add_argument(
        "--source",
        default="all",
        help="one of: all, " + ", ".join(BY_KEY),
    )
    parser.add_argument("--query", default="", help="keywords matched in title, company, or location")
    parser.add_argument("--where", default="", help="city or location text; LinkedIn uses this as the city")
    parser.add_argument("--limit", type=int, default=5, help="jobs to print per source")
    parser.add_argument(
        "--boards",
        default="",
        help="comma-separated company slugs for Greenhouse, Lever, and Ashby",
    )
    parser.add_argument("--country", default="in", help="Adzuna country code, for example in or gb")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="print the LinkedIn search URL without opening the browser",
    )
    parser.add_argument(
        "--sort",
        default="",
        help=(
            "comma-separated keys: salary (desc), date (desc, added on), exp (asc). "
            "Override with _asc or _desc, for example salary_asc,date_asc or exp_desc"
        ),
    )
    parser.add_argument("--list", action="store_true", help="print source names and exit")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="start the jobs API (this is also what happens when no search flags are given)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="interface for the jobs API",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8001")),
        help="port for the jobs API",
    )
    return parser


def selected_sources(name: str) -> list[type]:
    key = name.strip().casefold()
    if key == "all":
        return list(CONNECTORS)
    connector = BY_KEY.get(key)
    if connector is None:
        known = ", ".join(["all", *BY_KEY])
        raise SystemExit(f"Unknown source '{name}'. Choose from: {known}")
    return [connector]


def parse_boards(raw: str) -> list[str] | None:
    boards = [part.strip() for part in raw.split(",") if part.strip()]
    return boards or None


def make_connector(cls: type, country: str):
    if cls is Adzuna:
        return cls(country=country)
    return cls()


def run_connector(
    cls: type,
    query: str,
    where: str,
    limit: int,
    boards: list[str] | None,
    country: str,
    open_browser: bool,
    posted_within_days: int | None = None,
    publish=None,
):
    started = time.perf_counter()
    event(cls.key, "info", "start")
    try:
        connector, jobs = _run_connector(
            cls, query, where, limit, boards, country, open_browser, posted_within_days, publish,
        )
    except Exception as exc:
        event(cls.key, "error", f"fetch failed: {exc}")
        raise
    for warning in getattr(connector, "warnings", []):
        event(cls.key, "warning", warning)
    elapsed = round(time.perf_counter() - started, 1)
    event(cls.key, "info", f"done jobs={len(jobs)} seconds={elapsed}")
    return connector, jobs


def _run_connector(
    cls: type,
    query: str,
    where: str,
    limit: int,
    boards: list[str] | None,
    country: str,
    open_browser: bool,
    posted_within_days: int | None = None,
    publish=None,
):
    connector = make_connector(cls, country)
    site_boards = boards if cls.key in SLUG_SOURCES else None
    streamed = False

    def on_batch(batch: list[Job]) -> None:
        nonlocal streamed
        streamed = True
        batch = [
            job
            for job in batch
            if is_tech_role(job.title) and keeps_india_hybrid_or_remote(job.location)
        ]
        if publish is not None and batch:
            publish(connector, batch)

    kwargs = {
        "query": query,
        "where": where,
        "limit": limit,
        "boards": site_boards,
    }
    if posted_within_days and (
        cls.key in SLUG_SOURCES or getattr(cls, "persist", "") == "sidecar"
    ):
        kwargs["posted_within_days"] = posted_within_days
    if publish is not None and (
        cls.key in SLUG_SOURCES or getattr(cls, "persist", "") == "sidecar"
    ):
        kwargs["on_batch"] = on_batch
    if cls.key == "linkedin":
        jobs = connector.fetch(**kwargs, open_browser=open_browser)
    else:
        jobs = connector.fetch(**kwargs)
    jobs = [
        job
        for job in jobs
        if is_tech_role(job.title) and keeps_india_hybrid_or_remote(job.location)
    ]
    if posted_within_days:
        jobs = [
            job
            for job in jobs
            if not job.posted_at or within_days(job.posted_at, posted_within_days)
        ]
    if publish is not None:
        publish(connector, [] if streamed else jobs)
    return connector, jobs


def run_sources(
    sources: list[type],
    query: str,
    where: str,
    limit: int,
    boards: list[str] | None,
    country: str,
    open_browser: bool,
    posted_within_days: int | None = None,
    publish=None,
) -> list[tuple]:
    results = []
    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as pool:
        futures = {
            pool.submit(
                run_connector,
                cls,
                query,
                where,
                limit,
                boards,
                country,
                open_browser,
                posted_within_days,
                publish,
            ): cls
            for cls in sources
        }
        for future in as_completed(futures):
            cls = futures[future]
            try:
                results.append((cls.key, future.result()))
            except Exception as exc:
                connector = make_connector(cls, country)
                connector.warnings = [str(exc)]
                if publish is not None:
                    publish(connector, [])
                results.append((cls.key, (connector, [])))
    order = {cls.key: index for index, cls in enumerate(sources)}
    return [item[1] for item in sorted(results, key=lambda item: order[item[0]])]


_SORT_FIELDS = {
    "salary": "salary",
    "date": "date",
    "added": "date",
    "addedon": "date",
    "added_on": "date",
    "exp": "exp",
    "experience": "exp",
}
_SORT_DESC_BY_DEFAULT = {"salary": True, "date": True, "exp": False}
_EXP_LEVELS = (
    ("intern", 0),
    ("junior", 1),
    ("bachelor", 2),
    ("master", 4),
    ("phd", 6),
    ("senior", 5),
    ("lead", 6),
    ("staff", 8),
    ("principal", 10),
    ("director", 12),
    ("head", 12),
)


def parse_sort(raw: str) -> list[tuple[str, bool]]:
    specs: list[tuple[str, bool]] = []
    for part in raw.split(","):
        token = part.strip().casefold().replace(" ", "").replace("-", "_")
        if not token:
            continue
        descending = None
        if token.endswith("_asc"):
            token = token[:-4]
            descending = False
        elif token.endswith("_desc"):
            token = token[:-5]
            descending = True
        field = _SORT_FIELDS.get(token)
        if field is None:
            raise SystemExit(
                f"Unknown sort key '{part.strip()}'. Use salary, date, or exp "
                "(optional _asc or _desc)."
            )
        if descending is None:
            descending = _SORT_DESC_BY_DEFAULT[field]
        specs.append((field, descending))
    return specs


def _amount(raw: str) -> float:
    text = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        return float(text.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", text):
        return float(text.replace(",", ""))
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
        return float(text)
    return float(text.replace(",", ""))


def _salary_value(text: str) -> float | None:
    if not text:
        return None
    numbers: list[float] = []
    for match in re.finditer(r"(\d[\d.,]*)\s*([kK])?", text):
        token = match.group(1).strip(".,")
        if not token or not re.search(r"\d", token):
            continue
        value = _amount(token)
        if match.group(2):
            value *= 1000
        numbers.append(value)
    if not numbers:
        return None
    return max(numbers)


def _experience_value(text: str) -> float | None:
    if not text:
        return None
    years = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:\+|plus)?(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?\s*years?",
        text,
        re.I,
    )
    if years:
        return float(years.group(1))
    folded = text.casefold()
    for word, rank in _EXP_LEVELS:
        if word in folded:
            return float(rank)
    return None


def _sort_value(job: Job, field: str):
    if field == "salary":
        return _salary_value(job.salary)
    if field == "date":
        return job.posted_at or None
    return _experience_value(job.experience)


def sort_jobs(jobs: list[Job], specs: list[tuple[str, bool]]) -> list[Job]:
    ordered = list(jobs)
    for field, descending in reversed(specs):
        def key(job: Job, field: str = field, descending: bool = descending):
            value = _sort_value(job, field)
            missing = value is None
            if descending:
                return (not missing, "" if missing else value)
            return (missing, "" if missing else value)

        ordered.sort(key=key, reverse=descending)
    return ordered


def job_record(job: Job, include_portal: bool, portal_key: str = "") -> dict:
    job = apply_posting_facts(job)
    record = {
        "company": job.company,
        "role": job.title,
        "experience": job.experience,
        "skill": job.skill,
        "salary": job.salary,
        "added on": job.posted_at,
        "location": job.location,
        "description": {
            "about company": job.about_company,
            "job description": job.job_description,
            **({"posted by": job.posted_by} if job.posted_by else {}),
            **({"email": job.poster_email} if job.poster_email else {}),
            **({"openings": job.openings} if job.openings else {}),
            **({"applicants": job.applicants} if job.applicants else {}),
        },
        "link": job.url,
        "apply": job.apply_url or job.url,
    }
    if include_portal:
        record = {"portal": job.source, "portalKey": portal_key, **record}
    return record


def print_jobs(jobs: list[Job], include_portal: bool) -> None:
    for job in jobs:
        print(json.dumps(job_record(job, include_portal), ensure_ascii=False, indent=2))


def print_source(connector, jobs: list[Job]) -> None:
    print()
    print(f"== {connector.label} ({len(jobs)}) ==")
    credit = CREDITS.get(connector.key)
    if credit and jobs:
        print(credit)
    for warning in connector.warnings:
        print(f"  note: {warning}")
    search = getattr(connector, "search_url", "")
    if connector.key == "linkedin" and search:
        print("CTA: open LinkedIn job search (you stay signed in as yourself)")
        print(search)
    elif search:
        print(search)
    if not jobs and not search:
        print("  No jobs matched.")
        return
    print_jobs(jobs, include_portal=False)


_TERMINAL_FLAGS = (
    "--source",
    "--query",
    "--where",
    "--limit",
    "--boards",
    "--sort",
    "--no-open",
    "--country",
    "--list",
)


def wants_terminal_output(argv: list[str]) -> bool:
    for arg in argv:
        name = arg.split("=", 1)[0]
        if name in _TERMINAL_FLAGS:
            return True
    return False


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    given = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(given)
    if args.list:
        for connector in CONNECTORS:
            print(connector.key)
        return
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")

    if args.serve or not wants_terminal_output(given):
        serve(args.host, args.port, args.country)
        return

    sources = selected_sources(args.source)
    sort_specs = parse_sort(args.sort)
    boards = parse_boards(args.boards)
    open_browser = not args.no_open
    print(
        f"fetchJobsForMe  source={args.source}  query={args.query or '-'}  "
        f"where={args.where or '-'}  limit={args.limit}  sort={args.sort or '-'}"
    )

    ordered_results = run_sources(
        sources,
        args.query,
        args.where,
        args.limit,
        boards,
        args.country,
        open_browser,
    )
    if args.source.strip().casefold() == "all":
        print_all_portals(ordered_results, sort_specs)
        return
    for connector, jobs in ordered_results:
        print_source(connector, sort_jobs(jobs, sort_specs))


def print_all_portals(results: list[tuple], sort_specs: list[tuple[str, bool]]) -> None:
    jobs: list[Job] = []
    print()
    print("== all portals ==")
    for connector, portal_jobs in results:
        credit = CREDITS.get(connector.key)
        if credit and portal_jobs:
            print(credit)
        for warning in connector.warnings:
            print(f"  note: {warning}")
        search = getattr(connector, "search_url", "")
        if connector.key == "linkedin" and search:
            print("CTA: open LinkedIn job search (you stay signed in as yourself)")
            print(search)
        jobs.extend(portal_jobs)
    jobs = sort_jobs(jobs, sort_specs)
    print(f"jobs: {len(jobs)}")
    if not jobs:
        print("  No jobs matched.")
        return
    print_jobs(jobs, include_portal=True)


def read_jobs_file() -> dict | None:
    try:
        payload = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return None
    return payload


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    body = json.dumps(payload, ensure_ascii=False)
    for attempt in range(5):
        try:
            temporary.write_text(body, encoding="utf-8")
            temporary.replace(path)
            return
        except OSError:
            time.sleep(0.3 * (attempt + 1))
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        event("api", "error", f"could not save {path.name}: {exc}")


def write_jobs_file(payload: dict) -> None:
    _write_json(JOBS_FILE, payload)


SAVED_FILE = JOBS_FILE.parent / "saved_jobs.json"
_saved_lock = threading.Lock()
_SAVED_FIELDS = (
    "portal", "portalKey", "company", "role", "experience",
    "skill", "salary", "added on", "location", "link", "apply",
)


def read_saved() -> list[dict]:
    try:
        payload = json.loads(SAVED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("link")]


def _saved_record(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("job must be an object")
    link = str(record.get("link") or "").strip()
    if not link.startswith(("http://", "https://")):
        raise ValueError("job needs an http(s) link")
    clean = {field: str(record.get(field) or "") for field in _SAVED_FIELDS}
    clean["link"] = link
    apply = str(record.get("apply") or "").strip()
    clean["apply"] = apply if apply.startswith(("http://", "https://")) else link
    description = record.get("description") if isinstance(record.get("description"), dict) else {}
    clean["description"] = {
        "about company": str(description.get("about company") or ""),
        "job description": str(description.get("job description") or ""),
    }
    for field in ("openings", "applicants", "posted by", "email"):
        value = str(description.get(field) or "").strip()
        if value:
            clean["description"][field] = value
    return with_portal_key(clean)


def save_job(record: dict) -> dict:
    job = _saved_record(record)
    with _saved_lock:
        saved = read_saved()
        existing = next((item for item in saved if item["link"] == job["link"]), None)
        if existing is not None:
            return existing
        job["saved at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _write_json(SAVED_FILE, [job, *saved])
    event(job.get("portalKey") or "saved", "info", f"saved {job['role']} — {job['company']}")
    return job


def unsave_job(link: str) -> bool:
    with _saved_lock:
        saved = read_saved()
        remaining = [item for item in saved if item["link"] != link]
        if len(remaining) == len(saved):
            return False
        _write_json(SAVED_FILE, remaining)
    event("saved", "info", f"removed {link}")
    return True


PREFERENCES_DIR = JOBS_FILE.parent / "preferences"
_preferences_lock = threading.Lock()
_POSTED_DAYS = {"today": 1, "yesterday": 2, "7days": 7, "15days": 15}
_EXP_TEXT = (
    (re.compile(r"\b(?:intern|internship|fresher|freshers|graduate|entry[- ]level|trainee)\b", re.I), 0),
    (re.compile(r"\bjunior\b", re.I), 1),
    (re.compile(r"\b(?:mid[- ]level|intermediate)\b", re.I), 2),
    (re.compile(r"\bsenior\b", re.I), 3),
    (re.compile(r"\b(?:lead|staff|principal|architect|manager)\b", re.I), 5),
)


def _preference_file(uid: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(uid or ""))[:128]
    if not safe:
        raise ValueError("user id is required")
    return PREFERENCES_DIR / f"{safe}.json"


def _empty_preferences() -> dict:
    return {"experience": None, "posted": "all", "roles": [], "updatedAt": ""}


def _experience_setting(value):
    from Server.feeds import experience_cap

    if value is None or str(value).strip().casefold() in {"", "all", "select"}:
        return None
    cap = experience_cap(value)
    if cap is None:
        raise ValueError("experience must be Select or a number from 0 to 5")
    return cap


def _posted_setting(value: str) -> str:
    posted = str(value or "all").strip().casefold()
    if posted in {"", "select", "all"}:
        return "all"
    if posted not in _POSTED_DAYS:
        raise ValueError("posted must be Select, today, yesterday, 7days, or 15days")
    return posted


def read_preferences(uid: str) -> dict:
    result = _empty_preferences()
    try:
        payload = json.loads(_preference_file(uid).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return result
    if not isinstance(payload, dict):
        return result
    try:
        result["experience"] = _experience_setting(payload.get("experience"))
    except ValueError:
        result["experience"] = None
    try:
        result["posted"] = _posted_setting(payload.get("posted"))
    except ValueError:
        result["posted"] = "all"
    roles = payload.get("roles")
    if isinstance(roles, list):
        result["roles"] = list(dict.fromkeys(
            clean(str(role))[:80] for role in roles if clean(str(role))
        ))[:20]
    result["updatedAt"] = str(payload.get("updatedAt") or "")
    return result


def update_preferences(uid: str, changes: dict) -> dict:
    if not isinstance(changes, dict):
        raise ValueError("preferences must be an object")
    experience = _experience_setting(changes.get("experience"))
    posted = _posted_setting(changes.get("posted"))
    roles = changes.get("roles")
    if not isinstance(roles, list):
        raise ValueError("roles must be a list")
    preferences = {
        "experience": experience,
        "posted": posted,
        "roles": list(dict.fromkeys(
            clean(str(role))[:80] for role in roles if clean(str(role))
        ))[:20],
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _preferences_lock:
        _write_json(_preference_file(uid), preferences)
    event("preferences", "info", f"updated uid={uid[:8]} roles={len(preferences['roles'])}")
    return preferences


def preference_days(preferences: dict) -> int:
    return _POSTED_DAYS.get(str(preferences.get("posted") or ""), WINDOW_DAYS)


def _feed_preferences(preferences: dict) -> dict:
    from Server.feeds import experience_cap

    return {
        "windowDays": preference_days(preferences),
        "experience": experience_cap(preferences.get("experience")),
        "roles": preferences.get("roles") or [],
    }


def _minimum_experience(record: dict) -> int | None:
    text = clean(f"{record.get('experience') or ''} {record.get('role') or ''}")
    experience = clean(record.get("experience"))
    numbers = [int(value) for value in re.findall(r"\d{1,2}", experience)]
    if numbers:
        return min(numbers)
    for pattern, years in _EXP_TEXT:
        if pattern.search(text):
            return years
    return None


def _matches_preferences(record: dict, preferences: dict) -> bool:
    posted = str(record.get("added on") or "")
    days = preference_days(preferences)
    if posted and not within_days(posted, days):
        return False
    from Server.feeds import experience_cap, role_matches

    minimum = _minimum_experience(record)
    cap = experience_cap(preferences.get("experience"))
    if cap is not None and minimum is not None and minimum > cap:
        return False
    return role_matches(record.get("role") or "", record.get("skill") or "", preferences.get("roles") or [])


def apply_preferences(payload: dict, preferences: dict) -> dict:
    result = dict(payload)
    result["jobs"] = [
        record for record in payload.get("jobs") or []
        if _matches_preferences(record, preferences)
    ]
    result["count"] = len(result["jobs"])
    result["preferences"] = preferences
    return result


# Candidate profile and resume. The profile is deliberately provider-neutral so
# recommendations, applications, and future agents can all consume one schema.

MAX_RESUME_BYTES = 8 * 1024 * 1024
_profile_lock = threading.Lock()
_PROFILE_TEXT_FIELDS = (
    "fullName", "email", "phone", "headline", "summary", "currentTitle",
    "currentCompany", "totalExperience", "noticePeriod", "expectedSalary",
    "salaryCurrency", "linkedin", "github", "portfolio", "workAuthorization",
    "education", "experienceHistory",
)
_PROFILE_LIST_FIELDS = (
    "skills", "targetRoles", "preferredLocations", "workModes", "employmentTypes",
)
_PROFILE_BOOL_FIELDS = ("openToWork", "willingToRelocate")
_SKILL_TERMS = (
    "Python", "Java", "JavaScript", "TypeScript", "React", "Angular", "Vue",
    "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring Boot", ".NET",
    "C", "C++", "C#", "Go", "Rust", "Kotlin", "Swift", "PHP", "Ruby",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Oracle", "Snowflake",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Jenkins",
    "Git", "Linux", "REST", "GraphQL", "Kafka", "Spark", "Hadoop", "Airflow",
    "Machine Learning", "Deep Learning", "NLP", "TensorFlow", "PyTorch",
    "Pandas", "NumPy", "Data Analysis", "Power BI", "Tableau", "Selenium",
    "Cypress", "Playwright", "API Testing", "Agile", "Scrum", "DevOps",
    "Microservices", "System Design", "Data Structures", "Algorithms",
)


def _empty_profile() -> dict:
    profile = {field: "" for field in _PROFILE_TEXT_FIELDS}
    profile.update({field: [] for field in _PROFILE_LIST_FIELDS})
    profile.update({field: False for field in _PROFILE_BOOL_FIELDS})
    profile.update({
        "resume": None,
        "updatedAt": "",
    })
    return profile


def _profile_completion(profile: dict) -> int:
    important = (
        "fullName", "email", "phone", "headline", "summary", "currentTitle",
        "totalExperience", "skills", "targetRoles", "preferredLocations",
        "workModes", "education", "experienceHistory", "resume",
    )
    complete = sum(bool(profile.get(field)) for field in important)
    return round(complete * 100 / len(important))

def _profile_document(uid: str):
    uid = str(uid or "").strip()

    if not uid:
        raise ValueError("authenticated user UID is required")

    return (
        get_firestore_client()
        .collection("users")
        .document(uid)
        .collection("jobProfile")
        .document("default")
    )

def read_profile(uid: str) -> dict:
    profile = _empty_profile()

    try:
        snapshot = _profile_document(uid).get()
        payload = snapshot.to_dict() if snapshot.exists else {}
    except Exception as exc:
        event(
            "profile",
            "error",
            f"profile read failed uid={uid}: {exc}",
        )
        raise ValueError("could not read profile") from exc

    if not isinstance(payload, dict):
        payload = {}

    for field in _PROFILE_TEXT_FIELDS:
        value = payload.get(field)
        if isinstance(value, str):
            profile[field] = value

    for field in _PROFILE_LIST_FIELDS:
        value = payload.get(field)

        if isinstance(value, list):
            profile[field] = list(
                dict.fromkeys(
                    str(item).strip()
                    for item in value
                    if str(item).strip()
                )
            )[:100]

    for field in _PROFILE_BOOL_FIELDS:
        profile[field] = bool(payload.get(field, False))

    resume = payload.get("resume")

    if isinstance(resume, dict):
        profile["resume"] = resume

    profile["updatedAt"] = str(payload.get("updatedAt") or "")
    profile["completion"] = _profile_completion(profile)

    return profile

def update_profile(uid: str, changes: dict) -> dict:
    if not isinstance(changes, dict):
        raise ValueError("profile must be an object")

    uid = str(uid or "").strip()

    if not uid:
        raise ValueError("authenticated user UID is required")

    with _profile_lock:
        profile = read_profile(uid)

        for field in _PROFILE_TEXT_FIELDS:
            if field in changes:
                profile[field] = str(
                    changes[field] or ""
                ).strip()[:10_000]

        for field in _PROFILE_LIST_FIELDS:
            if field not in changes:
                continue

            value = changes[field]

            if not isinstance(value, list):
                raise ValueError(f"{field} must be a list")

            profile[field] = list(
                dict.fromkeys(
                    str(item).strip()[:120]
                    for item in value
                    if str(item).strip()
                )
            )[:100]

        for field in _PROFILE_BOOL_FIELDS:
            if field in changes:
                profile[field] = bool(changes[field])

        profile["updatedAt"] = datetime.now(
            timezone.utc
        ).isoformat()

        profile.pop("completion", None)

        try:
            _profile_document(uid).set(profile, merge=True)
        except Exception as exc:
            event(
                "profile",
                "error",
                f"profile update failed uid={uid}: {exc}",
            )
            raise ValueError("could not update profile") from exc

    event("profile", "info", f"profile updated uid={uid}")

    return read_profile(uid)

def _resume_text(content: bytes, suffix: str) -> str:
    suffix = suffix.casefold()

    if suffix == ".txt":
        return content.decode("utf-8", errors="replace")

    if suffix == ".docx":
        return _docx_resume_text(content)

    if suffix == ".pdf":
        return _pdf_resume_text(content)

    raise ValueError("resume must be a PDF, DOCX, or TXT file")

def _docx_resume_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")

        root = ElementTree.fromstring(xml)

    except (
        KeyError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ) as exc:
        raise ValueError("invalid DOCX resume") from exc

    namespace = (
        "{http://schemas.openxmlformats.org/"
        "wordprocessingml/2006/main}"
    )

    paragraphs = []

    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(
            node.text or ""
            for node in paragraph.iter(f"{namespace}t")
        ).strip()

        if text:
            paragraphs.append(text)

    extracted = "\n".join(paragraphs).strip()

    if len(extracted) < 20:
        raise ValueError(
            "could not extract enough text from the DOCX resume"
        )

    return extracted

def _pdf_resume_text(content: bytes) -> str:
    errors = []

    # First parser: pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=False)

        if reader.is_encrypted:
            decrypt_result = reader.decrypt("")

            if decrypt_result == 0:
                raise ValueError(
                    "password-protected PDF is not supported"
                )

        pages = []

        for page in reader.pages:
            try:
                text = page.extract_text(
                    extraction_mode="layout"
                ) or ""
            except TypeError:
                # For older pypdf versions without extraction_mode.
                text = page.extract_text() or ""

            if text.strip():
                pages.append(text)

        extracted = "\n".join(pages).strip()

        if len(extracted) >= 20:
            return extracted

        errors.append("pypdf returned insufficient text")

    except Exception as exc:
        errors.append(f"pypdf: {exc}")

    # Second parser: PyMuPDF
    try:
        import fitz

        document = fitz.open(
            stream=content,
            filetype="pdf",
        )

        pages = []

        for page in document:
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda block: (block[1], block[0]))

            page_text = "\n".join(
                str(block[4]).strip()
                for block in blocks
                if len(block) > 4 and str(block[4]).strip()
            )

            if page_text:
                pages.append(page_text)

        document.close()

        extracted = "\n".join(pages).strip()

        if len(extracted) >= 20:
            return extracted

        errors.append("PyMuPDF returned insufficient text")

    except Exception as exc:
        errors.append(f"PyMuPDF: {exc}")

    event(
        "profile",
        "error",
        "PDF extraction failed: " + "; ".join(errors),
    )

    raise ValueError(
        "This PDF contains insufficient selectable text. "
        "Upload a text-based PDF or DOCX file. "
        "A scanned or image-only PDF requires OCR."
    )


import re
from typing import Optional


# Canonical headings supported by the parser.
_SECTION_HEADINGS = {
    "summary": {
        "summary",
        "profile",
        "professional summary",
        "career summary",
        "executive summary",
        "about me",
    },
    "skills": {
        "skills",
        "skill summary",
        "skills summary",
        "technical skills",
        "core skills",
        "core competencies",
        "technologies",
        "technical expertise",
    },
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "career history",
    },
    "certifications": {
        "certification",
        "certifications",
        "certifications and achievements",
        "certifications & achievements",
        "achievements",
        "awards",
        "awards and achievements",
        "awards & achievements",
    },
    "education": {
        "education",
        "academic background",
        "academic qualifications",
        "qualifications",
        "educational qualifications",
    },
    "projects": {
        "projects",
        "project experience",
        "personal projects",
        "academic projects",
    },
}

def _normalize_heading(value: str) -> str:
    value = str(value or "").strip()

    value = re.sub(r"^[\s#*_•\-–—:|]+", "", value)
    value = re.sub(r"[\s#*_•\-–—:|]+$", "", value)
    value = re.sub(r"\s*&\s*", " and ", value)
    value = re.sub(r"\s+", " ", value)

    return value.casefold().strip()

def _heading_type(line: str) -> Optional[str]:
    normalized = _normalize_heading(line)

    if not normalized or len(normalized) > 80:
        return None

    for section_type, headings in _SECTION_HEADINGS.items():
        normalized_headings = {
            _normalize_heading(heading)
            for heading in headings
        }

        if normalized in normalized_headings:
            return section_type

    return None

def _clean_resume_lines(text: str) -> list[str]:
    text = str(text or "").replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    cleaned = []

    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()

        line = re.sub(r"^\*+\s*", "", line)
        line = re.sub(r"\s*\*+$", "", line)

        if line:
            cleaned.append(line)

    return cleaned

def _extract_section(lines: list[str], section_name: str) -> str:
    """
    Extract one section and stop at the next recognized heading.

    This prevents Certifications, Achievements and Education from being
    included in experience history.
    """
    start_index = None

    for index, line in enumerate(lines):
        if _heading_type(line) == section_name:
            start_index = index + 1
            break

    if start_index is None:
        return ""

    selected = []

    for line in lines[start_index:]:
        if _heading_type(line) is not None:
            break

        selected.append(line)

    return "\n".join(selected).strip()[:10_000]


def _looks_like_contact_line(line: str) -> bool:
    folded = line.casefold()

    return bool(
        "@" in line
        or "linkedin" in folded
        or "github" in folded
        or re.search(r"\+?\d[\d\s\-()]{8,}", line)
    )


def _extract_name(lines: list[str]) -> str:
    for line in lines[:10]:
        if _heading_type(line):
            break

        if _looks_like_contact_line(line):
            continue

        candidate = re.sub(
            r"\b(?:email|mobile|phone|linkedin)\s*:.*$",
            "",
            line,
            flags=re.I,
        ).strip()

        words = candidate.split()

        if (
            2 <= len(words) <= 5
            and len(candidate) <= 70
            and not re.search(r"\d", candidate)
        ):
            return candidate.title() if candidate.isupper() else candidate

    return ""

def _extract_current_employment(
    experience_text: str,
) -> tuple[str, str]:

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in experience_text.splitlines()
        if line.strip()
    ]

    if not lines:
        return "", ""

    title = ""
    company = ""

    for line in lines[:5]:

        if line.lower().startswith("client:"):
            continue

        if line.startswith(("•", "-", "*")):
            continue

        header = line

        match = re.match(
            r"^(?P<title>.+?)\s*(?:—|–|-| at )\s*(?P<company>.+)$",
            header,
            re.I,
        )

        if match:
            title = match.group("title").strip()
            company_text = match.group("company").strip()

            company = company_text.split(",")[0].strip()
            break

        parts = [p.strip() for p in header.split(",") if p.strip()]

        if len(parts) >= 2:
            title = parts[0]
            company = parts[1]
            break

    return title[:150], company[:150]
def _extract_total_experience(
    text: str,
    summary: str,
) -> str:

    search_text = summary or text

    patterns = (
        r"\b(?:over|more than)\s+(?P<value>\d+(?:\.\d+)?)\s+years?\b",
        r"\b(?P<value>\d+(?:\.\d+)?)\s*\+?\s+years?(?:\s+of)?\s+(?:professional\s+)?experience\b",
        r"\bexperience\s+of\s+(?P<value>\d+(?:\.\d+)?)\s*\+?\s+years?\b",
        r"\b(?P<article>an|one)\s+year\s+of\s+experience\b",
    )

    for pattern in patterns:

        match = re.search(pattern, search_text, re.I)

        if not match:
            continue

        if match.groupdict().get("value"):
            value = float(match.group("value"))

            if 0 < value <= 50:
                return f"{value:g} years"

        if match.groupdict().get("article"):
            return "1 year"

    return ""


def _extract_notice_period(text: str) -> str:
    patterns = (
        r"\bnotice period\s*[:\-]?\s*([^\n|,;]+)",
        r"\b(?:available|availability)\s*[:\-]?\s*([^\n|,;]+)",
        r"\b(immediate joiner)\b",
        r"\b(serving notice period)\b",
    )

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            value = match.group(1).strip()
            return value[:120]

    return ""

def _extract_skills(skills_text: str, full_text: str) -> list[str]:

    source_text = skills_text or full_text
    folded = source_text.casefold()

    discovered = []

    for skill in _SKILL_TERMS:

        pattern = (
            rf"(?<![a-z0-9])"
            rf"{re.escape(skill.casefold())}"
            rf"(?![a-z0-9])"
        )

        if re.search(pattern, folded):
            discovered.append(skill)

    return discovered
def parse_resume(text: str) -> dict:

    lines = _clean_resume_lines(text)
    joined = "\n".join(lines)

    email_match = re.search(
        r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
        joined,
    )

    phone_match = re.search(
        r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)",
        joined,
    )

    urls = re.findall(
        r"https?://[^\s|,;]+|(?:linkedin\.com|github\.com)/[^\s|,;]+",
        joined,
        re.I,
    )

    summary = _extract_section(lines, "summary")
    skills_text = _extract_section(lines, "skills")
    experience = _extract_section(lines, "experience")
    education = _extract_section(lines, "education")

    current_title, current_company = _extract_current_employment(
        experience
    )

    skills = _extract_skills(
        skills_text,
        joined,
    )

    linkedin = next(
        (
            url.rstrip(".)]")
            for url in urls
            if "linkedin.com" in url.casefold()
        ),
        "",
    )

    github = next(
        (
            url.rstrip(".)]")
            for url in urls
            if "github.com" in url.casefold()
        ),
        "",
    )

    portfolio = next(
        (
            url.rstrip(".)]")
            for url in urls
            if url not in {linkedin, github}
        ),
        "",
    )

    return {
        "fullName": _extract_name(lines),
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "headline": current_title,
        "currentTitle": current_title,
        "currentCompany": current_company,
        "summary": summary,
        "totalExperience": _extract_total_experience(
            joined,
            summary,
        ),
        "noticePeriod": _extract_notice_period(joined),
        "skills": skills,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
        "education": education,
        "experienceHistory": experience,
    }


def upload_resume(uid: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("resume payload must be an object")

    uid = str(uid or "").strip()

    if not uid:
        raise ValueError("authenticated user UID is required")

    filename = Path(
        str(payload.get("filename") or "")
    ).name

    suffix = Path(filename).suffix.casefold()

    if suffix not in {".pdf", ".docx", ".txt"}:
        raise ValueError(
            "resume must be a PDF, DOCX, or TXT file"
        )

    encoded = payload.get("content")

    if not isinstance(encoded, str):
        raise ValueError("resume content is required")

    try:
        content = base64.b64decode(
            encoded,
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "resume content must be valid base64"
        ) from exc

    if not content:
        raise ValueError("resume is empty")

    if len(content) > MAX_RESUME_BYTES:
        raise ValueError(
            "resume must be 8 MB or smaller"
        )

    text = _resume_text(content, suffix)

    if len(text.strip()) < 20:
        raise ValueError(
            "could not extract enough text from this resume"
        )

    extracted = parse_resume(text)

    uploaded_at = datetime.now(
        timezone.utc
    ).isoformat()

    with _profile_lock:
        profile = read_profile(uid)

        # Update only fields that were successfully extracted.
        # Existing manually entered data remains unchanged when
        # the parser cannot identify a value.
        for field, value in extracted.items():
            if value:
                profile[field] = value

        profile["resume"] = {
            "filename": filename,
            "size": len(content),
            "uploadedAt": uploaded_at,
            "type": suffix.lstrip(".").upper(),
        }

        profile["updatedAt"] = uploaded_at
        profile.pop("completion", None)

        try:
            _profile_document(uid).set(
                profile,
                merge=True,
            )
        except Exception as exc:
            event(
                "profile",
                "error",
                (
                    "resume profile save failed "
                    f"uid={uid}: {exc}"
                ),
            )
            raise ValueError(
                "could not save parsed resume profile"
            ) from exc

    event(
        "profile",
        "info",
        (
            f"resume parsed uid={uid} "
            f"filename={filename} "
            f"bytes={len(content)}"
        ),
    )

    return {
        "profile": read_profile(uid),
        "extracted": extracted,
    }

SNAPSHOT_VERSION = 3


def _snapshot_current(saved: dict) -> bool:
    return (
        saved.get("windowDays") == WINDOW_DAYS
        and saved.get("version") == SNAPSHOT_VERSION
        and not saved.get("loading")
    )


def _portal_list() -> list[dict]:
    return _portal_catalog()


_LABEL_TO_KEY = {cls.label.casefold(): cls.key for cls in CONNECTORS}


def with_portal_key(record: dict) -> dict:
    if not isinstance(record, dict):
        return record
    key = (record.get("portalKey") or "").strip()
    if not key:
        key = _LABEL_TO_KEY.get((record.get("portal") or "").strip().casefold(), "")
    if not key or record.get("portalKey") == key:
        return record
    return {**record, "portalKey": key}


def with_note_key(note: dict) -> dict:
    if not isinstance(note, dict):
        return note
    key = (note.get("portalKey") or "").strip()
    if not key:
        key = _LABEL_TO_KEY.get((note.get("portal") or "").strip().casefold(), "")
    if not key or note.get("portalKey") == key:
        return note
    return {**note, "portalKey": key}


def _portal_catalog() -> list[dict]:
    live = FEED_COORDINATOR.status()
    main_running = bool(_progress.get("running"))
    catalog = []
    for cls in CONNECTORS:
        info = live.get(cls.key, {})
        if cls.key in PAUSED_SIDECAR_KEYS:
            status = "paused"
        elif info.get("running"):
            status = "running"
        elif getattr(cls, "persist", "") != "sidecar" and main_running:
            status = "running"
        elif info.get("error"):
            status = "error"
        else:
            status = "idle"
        catalog.append({
            "key": cls.key,
            "label": cls.label,
            "status": status,
            "warnings": list(info.get("warnings") or []),
            "error": info.get("error") or "",
            "seconds": info.get("seconds"),
        })
    return catalog


def _respond(payload: dict) -> dict:
    merged = FEED_COORDINATOR.merge(payload, CREDITS)
    merged["jobs"] = [with_portal_key(record) for record in merged.get("jobs") or []]
    merged["notes"] = [with_note_key(note) for note in merged.get("notes") or []]
    merged["portals"] = _portal_catalog()
    return merged


def _payload_from_progress(loading: bool, cached: bool = False) -> dict:
    jobs = list(_progress["jobs"])
    return {
        "source": "all",
        "query": "",
        "where": "",
        "limit": 0,
        "count": len(jobs),
        "jobs": jobs,
        "portals": _portal_list(),
        "credits": list(_progress["credits"]),
        "notes": list(_progress["notes"]),
        "windowDays": WINDOW_DAYS,
        "version": SNAPSHOT_VERSION,
        "loading": loading,
        "cached": cached,
        "fetchedAt": "" if loading else _progress["fetchedAt"],
        "error": _progress["error"],
        "stopped": bool(_progress.get("stopped")),
    }


def _remember(generation: int, connector, batch: list[Job], preferences: dict | None = None) -> None:
    with _jobs_lock:
        if generation != _progress["generation"]:
            return
        for job in batch:
            record = job_record(job, include_portal=True, portal_key=connector.key)
            if preferences and not _matches_preferences(record, preferences):
                continue
            link = record.get("link") or ""
            if not link:
                continue
            position = _progress["index"].get(link)
            if position is None:
                _progress["index"][link] = len(_progress["jobs"])
                _progress["jobs"].append(record)
            else:
                _progress["jobs"][position] = record
        credit = CREDITS.get(connector.key)
        if credit and batch and credit not in _progress["credits"]:
            _progress["credits"].append(credit)
        for warning in connector.warnings:
            key = (connector.label, warning)
            if key in _progress["note_keys"]:
                continue
            _progress["note_keys"].add(key)
            _progress["notes"].append({
                "portal": connector.label,
                "portalKey": connector.key,
                "message": warning,
            })
        now = time.monotonic()
        if batch and now - _progress.get("last_write", 0.0) >= 0.6:
            write_jobs_file(_payload_from_progress(loading=not _progress.get("stopped")))
            _progress["last_write"] = now


def _finish_fetch(generation: int, error: str = "") -> None:
    with _jobs_lock:
        if generation != _progress["generation"]:
            return
        _progress["running"] = False
        _progress["error"] = error
        _progress["fetchedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if error:
            _progress["notes"].append({"portal": "fetch", "portalKey": "", "message": error})
            event("jobs", "error", error)
        else:
            event("jobs", "info", f"company boards done jobs={len(_progress['jobs'])}")
        payload = _payload_from_progress(loading=False)
        write_jobs_file(payload)


def _portal_sources() -> list[type]:
    return [cls for cls in CONNECTORS if getattr(cls, "persist", "") != "sidecar"]


def _fetch_worker(country: str, generation: int, preferences: dict) -> None:
    event("jobs", "info", "company boards start")
    try:
        run_sources(
            _portal_sources(),
            query="",
            where="",
            limit=0,
            boards=None,
            country=country,
            open_browser=False,
            posted_within_days=preference_days(preferences),
            publish=lambda connector, batch: _remember(generation, connector, batch, preferences),
        )
    except Exception as exc:
        _finish_fetch(generation, error=str(exc))
        return
    _finish_fetch(generation)


def _reset_progress() -> None:
    _progress["generation"] += 1
    _progress["running"] = True
    _progress["jobs"] = []
    _progress["index"] = {}
    _progress["notes"] = []
    _progress["note_keys"] = set()
    _progress["credits"] = []
    _progress["error"] = ""
    _progress["fetchedAt"] = ""
    _progress["last_write"] = 0.0
    _progress["stopped"] = False
    arm()
    FEED_COORDINATOR.suppressed = False


def stop_fetches() -> dict:
    cancel()
    from connectors.Naukri.Naukri import close_naukri_browser

    close_naukri_browser()
    FEED_COORDINATOR.stop()
    with _jobs_lock:
        _progress["stopped"] = True
        _progress["running"] = False
        _progress["fetchedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        note = {"portal": "fetch", "portalKey": "", "message": "Stopped. Showing jobs saved so far."}
        if note not in _progress["notes"]:
            _progress["notes"].append(note)
        payload = _payload_from_progress(loading=False)
        write_jobs_file(payload)
    return _respond(payload)


def _start_main_fetch(country: str, refresh_sidecars: bool, preferences: dict) -> dict:
    with _jobs_lock:
        _reset_progress()
        generation = _progress["generation"]
        payload = _payload_from_progress(loading=True)
    FEED_COORDINATOR.start_all(refresh_sidecars, _feed_preferences(preferences))
    threading.Thread(
        target=_fetch_worker,
        args=(country, generation, preferences),
        name="jobs-fetch",
        daemon=True,
    ).start()
    return payload


def saved_or_live_jobs(country: str, refresh: bool, preferences: dict) -> dict:
    if refresh:
        payload = _start_main_fetch(country, True, preferences)
        return _respond(payload)

    saved = read_jobs_file()
    if held() or FEED_COORDINATOR.suppressed or _progress.get("stopped") or (saved or {}).get("stopped"):
        FEED_COORDINATOR.suppressed = True
        with _jobs_lock:
            if _progress.get("stopped") or _progress["jobs"]:
                payload = _payload_from_progress(loading=False)
            elif saved is not None:
                saved["cached"] = True
                saved["loading"] = False
                saved["stopped"] = True
                saved["portals"] = _portal_list()
                payload = saved
            else:
                payload = _payload_from_progress(loading=False)
        return _respond(payload)

    with _jobs_lock:
        if _progress["running"]:
            payload = _payload_from_progress(loading=True)
            running = True
        else:
            payload = None
            running = False
    if running:
        FEED_COORDINATOR.start_all(False, _feed_preferences(preferences))
        return _respond(payload)

    if saved is not None and _snapshot_current(saved):
        FEED_COORDINATOR.start_all(False, _feed_preferences(preferences))
        saved["cached"] = True
        saved["loading"] = False
        saved["portals"] = _portal_list()
        return _respond(saved)

    payload = _start_main_fetch(country, False, preferences)
    return _respond(payload)


def _current_view() -> dict:
    with _jobs_lock:
        live = _progress["running"] or bool(_progress["jobs"])
        payload = _payload_from_progress(loading=_progress["running"]) if live else None
    if payload is None:
        payload = read_jobs_file() or _payload_from_progress(loading=False)
    return _respond(payload)


def jobs_summary() -> dict:
    view = _current_view()
    counts: dict[str, int] = {}
    new_today = 0
    for record in view.get("jobs") or []:
        key = record.get("portalKey") or ""
        if key:
            counts[key] = counts.get(key, 0) + 1
        posted = record.get("added on") or ""
        if posted and within_days(posted, 1):
            new_today += 1
    sources = [
        {"key": portal["key"], "label": portal["label"], "status": portal["status"], "count": counts[portal["key"]]}
        for portal in view.get("portals") or []
        if counts.get(portal["key"])
    ]
    sources.sort(key=lambda source: source["count"], reverse=True)
    return {
        "sourcesConnected": len(sources),
        "sources": sources,
        "total": len(view.get("jobs") or []),
        "newToday": new_today,
        "saved": len(read_saved()),
        "loading": bool(view.get("loading")),
        "fetchedAt": view.get("fetchedAt") or "",
    }


class JobsApiHandler(BaseHTTPRequestHandler):
    """JSON API for the web app. Jobs are read-only; saved jobs accept POST and DELETE."""

    max_body = 12 * 1024 * 1024
    server_version = "fetchJobsForMe"
    country = "in"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self) -> None:
        route = urlparse(self.path)
        params = parse_qs(route.query)
        if route.path == "/api/health":
            self._send_json(200, {"status": "ok"})
            return
        if route.path == "/api/jobs/stop":
            self._send_json(200, stop_fetches())
            return
        if route.path == "/api/portals":
            self._send_json(200, {"portals": _portal_catalog()})
            return
        if route.path == "/api/saved":
            saved = read_saved()
            self._send_json(200, {"jobs": saved, "count": len(saved)})
            return
        if route.path == "/api/summary":
            self._send_json(200, jobs_summary())
            return
        if route.path == "/api/profile":
            self._send_json(200, {"profile": read_profile()})
            return
        if route.path == "/api/preferences":
            uid = (params.get("uid") or [""])[0].strip()
            if not uid:
                self._send_json(400, {"error": "uid is required"})
                return
            self._send_json(200, {"preferences": read_preferences(uid)})
            return
        if route.path != "/api/jobs":
            self._send_json(404, {"error": f"unknown path {route.path}"})
            return

        first = lambda name, fallback="": (params.get(name) or [fallback])[0].strip()
        refresh = first("refresh", "").casefold() in {"1", "true", "yes"}
        uid = first("uid")
        preferences = read_preferences(uid) if uid else _empty_preferences()
        try:
            payload = saved_or_live_jobs(
                country=first("country", self.country) or self.country,
                refresh=refresh,
                preferences=preferences,
            )
            payload = apply_preferences(payload, preferences)
        except SystemExit as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            event("api", "error", f"GET /api/jobs failed: {exc}")
            self._send_json(502, {"error": str(exc)})
            return
        self._send_json(200, payload)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        # Gemini AI Generation Endpoint
        if path == "/api/ai/generate":
            auth_header = self.headers.get("Authorization")
            try:
                client, uid = get_user_gemini_client(auth_header)
            except ValueError as exc:
                self._send_json(401, {"error": str(exc)})
                return
            except Exception as exc:
                self._send_json(500, {"error": f"Auth check failed: {exc}"})
                return

            body = self._read_json()
            if body is None:
                return

            prompt = str(body.get("prompt") or "").strip()
            if not prompt:
                self._send_json(400, {"error": "prompt is required"})
                return

            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                self._send_json(200, {"result": response.text})
            except Exception as exc:
                event("gemini", "error", f"Generation failed for uid={uid[:8]}: {exc}")
                self._send_json(502, {"error": f"Gemini error: {exc}"})
            return

        if path == "/api/resume":
            body = self._read_json()
            if body is None:
                return
            try:
                result = upload_resume(body)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, result)
            return

        if path != "/api/saved":
            self._send_json(404, {"error": f"unknown path {path}"})
            return
        body = self._read_json()
        if body is None:
            return
        try:
            job = save_job(body.get("job") if isinstance(body, dict) else None)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(201, {"job": job, "count": len(read_saved())})

    def do_PUT(self) -> None:
        route = urlparse(self.path)
        path = route.path
        if path not in {"/api/profile", "/api/preferences"}:
            self._send_json(404, {"error": f"unknown path {path}"})
            return
        body = self._read_json()
        if body is None:
            return
        if path == "/api/preferences":
            uid = (parse_qs(route.query).get("uid") or [""])[0].strip()
            try:
                preferences = update_preferences(
                    uid,
                    body.get("preferences") if isinstance(body, dict) else None,
                )
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, {"preferences": preferences})
            return
        try:
            profile = update_profile(body.get("profile") if isinstance(body, dict) else None)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, {"profile": profile})

    def do_DELETE(self) -> None:
        route = urlparse(self.path)
        if route.path != "/api/saved":
            self._send_json(404, {"error": f"unknown path {route.path}"})
            return
        link = (parse_qs(route.query).get("link") or [""])[0].strip()
        if not link:
            self._send_json(400, {"error": "link is required"})
            return
        removed = unsave_job(link)
        self._send_json(200 if removed else 404, {"removed": removed, "count": len(read_saved())})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > self.max_body:
            self._send_json(413, {"error": "request body too large"})
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "body must be JSON"})
            return None

    def log_message(self, fmt: str, *args) -> None:
        event("api", "info", f"{self.address_string()} {fmt % args}")

    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)


def serve(host: str, port: int, country: str) -> None:
    enable()
    handler = type("JobsApiHandler", (JobsApiHandler,), {"country": country})
    httpd = ThreadingHTTPServer((host, port), handler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    event("api", "info", f"listening on http://{display_host}:{port}")
    print(f"fetchJobsForMe API on http://{display_host}:{port}")
    print(f"  GET http://{display_host}:{port}/api/jobs?source=all&query=engineer")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        event("api", "info", "stopped")
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()