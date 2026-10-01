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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

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


from Server.api import POSTED_WINDOW_DAYS, Job, is_tech_role, keeps_india_hybrid_or_remote, within_days
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
from connectors.Shine import Shine
from connectors.TheMuse import TheMuse
from connectors.WeWorkRemotely import WeWorkRemotely
from connectors.WorkingNomads import WorkingNomads

SLUG_SOURCES = {"greenhouse", "lever", "ashby"}
# Instahyre connector code stays in tree, but live web fetch is paused (rate limits / slow).
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
    Instahyre,
    Himalayas,
    Jobicy,
    TheMuse,
    WorkingNomads,
    FourDayWeek,
    WeWorkRemotely,
]
BY_KEY = {connector.key: connector for connector in CONNECTORS}

# Last successful "all portals" fetch. The jobs page reads this on startup.
# Web fetches keep India, Indian hybrid, and remote openings from this window.
WINDOW_DAYS = POSTED_WINDOW_DAYS
JOBS_FILE = Path(__file__).resolve().parents[1] / "data" / "jobs.json"
_jobs_lock = threading.Lock()
# In-memory fetch. The jobs page reads this while portals are still running.
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
    parser.add_argument("--port", type=int, default=8001, help="port for the jobs API")
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
        # Board portals already published each company. This call records notes.
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
    """Run each connector in parallel and return (connector, jobs) in source order."""
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
        },
        "link": job.url,
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


# These flags mean "print jobs in the terminal". Anything else starts the API.
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
        serve(args.port, args.country)
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
    """OneDrive or an editor can lock the file for a moment. Retry, and never fail a request over it."""
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


# Starred jobs. Kept until the user removes them, so they outlive the 15-day feed window.
SAVED_FILE = JOBS_FILE.parent / "saved_jobs.json"
_saved_lock = threading.Lock()
_SAVED_FIELDS = (
    "portal", "portalKey", "company", "role", "experience",
    "skill", "salary", "added on", "location", "link",
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
    """Keep only the job fields the UI renders. Raises ValueError for a record that cannot be saved."""
    if not isinstance(record, dict):
        raise ValueError("job must be an object")
    link = str(record.get("link") or "").strip()
    if not link.startswith(("http://", "https://")):
        raise ValueError("job needs an http(s) link")
    clean = {field: str(record.get(field) or "") for field in _SAVED_FIELDS}
    clean["link"] = link
    description = record.get("description") if isinstance(record.get("description"), dict) else {}
    clean["description"] = {
        "about company": str(description.get("about company") or ""),
        "job description": str(description.get("job description") or ""),
    }
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


# Candidate profile and resume. The profile is deliberately provider-neutral so
# recommendations, applications, and future agents can all consume one schema.
PROFILE_FILE = JOBS_FILE.parent / "profile.json"
RESUME_DIR = JOBS_FILE.parent / "resume"
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


def read_profile() -> dict:
    profile = _empty_profile()
    try:
        payload = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict):
        for field in _PROFILE_TEXT_FIELDS:
            if isinstance(payload.get(field), str):
                profile[field] = payload[field]
        for field in _PROFILE_LIST_FIELDS:
            if isinstance(payload.get(field), list):
                profile[field] = [str(item).strip() for item in payload[field] if str(item).strip()]
        for field in _PROFILE_BOOL_FIELDS:
            profile[field] = bool(payload.get(field))
        if isinstance(payload.get("resume"), dict):
            profile["resume"] = payload["resume"]
        profile["updatedAt"] = str(payload.get("updatedAt") or "")
    profile["completion"] = _profile_completion(profile)
    return profile


def update_profile(changes: dict) -> dict:
    if not isinstance(changes, dict):
        raise ValueError("profile must be an object")
    with _profile_lock:
        profile = read_profile()
        for field in _PROFILE_TEXT_FIELDS:
            if field in changes:
                profile[field] = str(changes[field] or "").strip()[:10_000]
        for field in _PROFILE_LIST_FIELDS:
            if field not in changes:
                continue
            value = changes[field]
            if not isinstance(value, list):
                raise ValueError(f"{field} must be a list")
            profile[field] = list(dict.fromkeys(
                str(item).strip()[:120] for item in value if str(item).strip()
            ))[:100]
        for field in _PROFILE_BOOL_FIELDS:
            if field in changes:
                profile[field] = bool(changes[field])
        profile["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        profile.pop("completion", None)
        _write_json(PROFILE_FILE, profile)
    event("profile", "info", "profile updated")
    return read_profile()


def _resume_text(content: bytes, suffix: str) -> str:
    if suffix == ".txt":
        return content.decode("utf-8", errors="replace")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise ValueError("invalid DOCX resume") from exc
        paragraphs = []
        for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            text = "".join(
                node.text or ""
                for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
            ).strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF parsing requires the pypdf package from backend/requirements.txt") from exc
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            if reader.is_encrypted:
                reader.decrypt("")
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages).strip()
            if not text:
                raise ValueError("This PDF has no selectable text. Export it as DOCX, or upload a text-based PDF.")
            return text
        except ValueError:
            raise
        except Exception as exc:
            event("profile", "error", f"pdf parse failed: {exc}")
            raise ValueError(
                "This PDF could not be read. Export it as DOCX, or use a PDF with selectable text."
            ) from exc
    raise ValueError("resume must be a PDF, DOCX, or TXT file")


def _section(text: str, headings: tuple[str, ...], stops: tuple[str, ...]) -> str:
    lines = [line.strip() for line in text.splitlines()]
    start = next(
        (index + 1 for index, line in enumerate(lines) if line.casefold().rstrip(":") in headings),
        None,
    )
    if start is None:
        return ""
    selected = []
    for line in lines[start:]:
        folded = line.casefold().rstrip(":")
        if folded in stops:
            break
        selected.append(line)
    return "\n".join(selected).strip()[:10_000]


def parse_resume(text: str) -> dict:
    """Conservative, deterministic resume extraction. The user reviews every result."""
    text = text.replace("\x00", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    joined = "\n".join(lines)
    email = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", joined)
    phone = re.search(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", re.sub(r"[() ]", "", joined))
    urls = re.findall(r"https?://[^\s|,;]+|(?:linkedin\.com|github\.com)/[^\s|,;]+", joined, re.I)

    name = ""
    for line in lines[:8]:
        if "@" in line or re.search(r"\d{6,}", line) or "http" in line.casefold():
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and len(line) <= 70:
            name = line
            break

    title = ""
    start = lines.index(name) + 1 if name in lines else 0
    for line in lines[start:start + 6]:
        if "@" not in line and not re.search(r"\d{6,}", line) and len(line) <= 100:
            title = line
            break

    skills = [
        skill for skill in _SKILL_TERMS
        if re.search(rf"(?<![a-z0-9]){re.escape(skill.casefold())}(?![a-z0-9])", joined.casefold())
    ]
    years = re.findall(r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*years?", joined, re.I)
    numeric_years = [float(value) for value in years if float(value) <= 50]
    total_experience = f"{max(numeric_years):g} years" if numeric_years else ""
    linkedin = next((url for url in urls if "linkedin.com" in url.casefold()), "")
    github = next((url for url in urls if "github.com" in url.casefold()), "")
    portfolio = next((url for url in urls if url not in {linkedin, github}), "")
    all_headings = (
        "experience", "work experience", "professional experience", "employment",
        "education", "academic background", "qualifications", "skills",
        "technical skills", "projects", "certifications", "summary", "profile",
    )
    experience = _section(
        joined,
        ("experience", "work experience", "professional experience", "employment"),
        all_headings,
    )
    education = _section(
        joined,
        ("education", "academic background", "qualifications"),
        all_headings,
    )
    summary = _section(joined, ("summary", "profile", "professional summary"), all_headings)
    return {
        "fullName": name,
        "email": email.group(0) if email else "",
        "phone": phone.group(0) if phone else "",
        "headline": title,
        "currentTitle": title,
        "summary": summary,
        "totalExperience": total_experience,
        "skills": skills,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
        "education": education,
        "experienceHistory": experience,
    }


def upload_resume(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("resume payload must be an object")
    filename = Path(str(payload.get("filename") or "")).name
    suffix = Path(filename).suffix.casefold()
    encoded = payload.get("content")
    if not isinstance(encoded, str):
        raise ValueError("resume content is required")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("resume content must be base64") from exc
    if not content:
        raise ValueError("resume is empty")
    if len(content) > MAX_RESUME_BYTES:
        raise ValueError("resume must be 8 MB or smaller")

    text = _resume_text(content, suffix)
    if len(text.strip()) < 20:
        raise ValueError("could not extract enough text from this resume")
    extracted = parse_resume(text)
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    for old in RESUME_DIR.glob("resume.*"):
        old.unlink(missing_ok=True)
    resume_path = RESUME_DIR / f"resume{suffix}"
    resume_path.write_bytes(content)

    with _profile_lock:
        profile = read_profile()
        # A new resume refreshes fields it can identify and preserves preferences
        # such as locations, work modes, salary, and manually entered values it cannot.
        for field, value in extracted.items():
            if value:
                profile[field] = value
        uploaded = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        profile["resume"] = {
            "filename": filename,
            "size": len(content),
            "uploadedAt": uploaded,
            "type": suffix.lstrip(".").upper(),
        }
        profile["updatedAt"] = uploaded
        profile.pop("completion", None)
        _write_json(PROFILE_FILE, profile)
    event("profile", "info", f"resume uploaded filename={filename} bytes={len(content)}")
    return {"profile": read_profile(), "extracted": extracted}


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
    """Attach the stable portal id. Saved rows that only have a display name still match."""
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
    """One row per portal: the id the UI filters on, plus live status for logs and later screens."""
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


def _remember(generation: int, connector, batch: list[Job]) -> None:
    """Add a portal's latest jobs. Same link replaces the earlier card (Greenhouse fills the description in a second pass)."""
    with _jobs_lock:
        if generation != _progress["generation"]:
            return
        for job in batch:
            record = job_record(job, include_portal=True, portal_key=connector.key)
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
    """Portals that share jobs.json; independent feeds use sidecar JSON files."""
    return [cls for cls in CONNECTORS if getattr(cls, "persist", "") != "sidecar"]


def _fetch_worker(country: str, generation: int) -> None:
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
            posted_within_days=WINDOW_DAYS,
            publish=lambda connector, batch: _remember(generation, connector, batch),
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
    """Stop every portal and keep the jobs already written to JSON."""
    cancel()
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


def _start_main_fetch(country: str, refresh_sidecars: bool) -> dict:
    with _jobs_lock:
        _reset_progress()
        generation = _progress["generation"]
        payload = _payload_from_progress(loading=True)
    FEED_COORDINATOR.start_all(refresh_sidecars)
    threading.Thread(
        target=_fetch_worker,
        args=(country, generation),
        name="jobs-fetch",
        daemon=True,
    ).start()
    return payload


def saved_or_live_jobs(country: str, refresh: bool) -> dict:
    """Return the saved file when it is complete. A new fetch returns jobs as each company comes in."""
    if refresh:
        payload = _start_main_fetch(country, True)
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
        FEED_COORDINATOR.start_all(False)
        return _respond(payload)

    if saved is not None and _snapshot_current(saved):
        FEED_COORDINATOR.start_all(False)
        saved["cached"] = True
        saved["loading"] = False
        saved["portals"] = _portal_list()
        return _respond(saved)

    payload = _start_main_fetch(country, False)
    return _respond(payload)


def _current_view() -> dict:
    """Jobs the page would show right now. Unlike /api/jobs this never starts a fetch."""
    with _jobs_lock:
        live = _progress["running"] or bool(_progress["jobs"])
        payload = _payload_from_progress(loading=_progress["running"]) if live else None
    if payload is None:
        payload = read_jobs_file() or _payload_from_progress(loading=False)
    return _respond(payload)


def jobs_summary() -> dict:
    """Numbers for Job Discovery: portals with jobs, jobs posted in 24 hours, saved jobs, last fetch."""
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

    def do_OPTIONS(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
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
        if route.path != "/api/jobs":
            self._send_json(404, {"error": f"unknown path {route.path}"})
            return

        first = lambda name, fallback="": (params.get(name) or [fallback])[0].strip()  # noqa: E731
        refresh = first("refresh", "").casefold() in {"1", "true", "yes"}
        try:
            payload = saved_or_live_jobs(
                country=first("country", self.country) or self.country,
                refresh=refresh,
            )
        except SystemExit as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception as exc:  # a portal failure should not kill the server
            event("api", "error", f"GET /api/jobs failed: {exc}")
            self._send_json(502, {"error": str(exc)})
            return
        self._send_json(200, payload)

    def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        path = urlparse(self.path).path
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

    def do_PUT(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        path = urlparse(self.path).path
        if path != "/api/profile":
            self._send_json(404, {"error": f"unknown path {path}"})
            return
        body = self._read_json()
        if body is None:
            return
        try:
            profile = update_profile(body.get("profile") if isinstance(body, dict) else None)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, {"profile": profile})

    def do_DELETE(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
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
        """Parse a JSON request body, or send 400/413 and return None."""
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)


def serve(port: int, country: str) -> None:
    enable()
    handler = type("JobsApiHandler", (JobsApiHandler,), {"country": country})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    event("api", "info", f"listening on http://127.0.0.1:{port}")
    print(f"fetchJobsForMe API on http://127.0.0.1:{port}")
    print(f"  GET http://127.0.0.1:{port}/api/jobs?source=all&query=engineer")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        event("api", "info", "stopped")
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
