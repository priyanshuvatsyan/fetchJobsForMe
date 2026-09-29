"""Connect to public job APIs and print openings in the terminal.

Examples (from the project root):
  python backend/Server/server.py --query engineer --where Bengaluru
  python backend/Server/server.py --source linkedin --query python --where Bengaluru
  python backend/Server/server.py --source greenhouse --boards groww --limit 5
  python backend/Server/server.py                    (start the jobs API for the web app)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from Server.api import Job, within_days
from connectors.Adzuna import Adzuna
from connectors.Arbeitnow import Arbeitnow
from connectors.Ashby import Ashby
from connectors.Greenhouse import Greenhouse
from connectors.Lever import Lever
from connectors.RemoteOK import RemoteOK
from connectors.Remotive import Remotive
from connectors.webScrapping import LinkedIn

SLUG_SOURCES = {"greenhouse", "lever", "ashby"}
CONNECTORS = [
    Greenhouse,
    Lever,
    Ashby,
    Remotive,
    RemoteOK,
    Arbeitnow,
    Adzuna,
    LinkedIn,
]
BY_KEY = {connector.key: connector for connector in CONNECTORS}

# Last successful "all portals" fetch. The jobs page reads this on startup.
# Web fetches keep every opening from the last 30 days, with no per-portal cap.
WINDOW_DAYS = 30
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
    "linkedin": "",
    "error": "",
    "fetchedAt": "",
    "last_write": 0.0,
}

CREDITS = {
    "remotive": "Credit: jobs from Remotive — https://remotive.com",
    "remoteok": "Credit: jobs from Remote OK — https://remoteok.com (link each job URL)",
    "adzuna": "Credit: Jobs by Adzuna — https://www.adzuna.com",
}


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
    connector = make_connector(cls, country)
    site_boards = boards if cls.key in SLUG_SOURCES else None
    streamed = False

    def on_batch(batch: list[Job]) -> None:
        nonlocal streamed
        streamed = True
        if publish is not None and batch:
            publish(connector, batch)

    kwargs = {
        "query": query,
        "where": where,
        "limit": limit,
        "boards": site_boards,
    }
    if posted_within_days and cls.key in SLUG_SOURCES:
        kwargs["posted_within_days"] = posted_within_days
    if publish is not None and cls.key in SLUG_SOURCES:
        kwargs["on_batch"] = on_batch
    if cls.key == "linkedin":
        jobs = connector.fetch(**kwargs, open_browser=open_browser)
    else:
        jobs = connector.fetch(**kwargs)
    if posted_within_days:
        jobs = [job for job in jobs if within_days(job.posted_at, posted_within_days)]
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


def job_record(job: Job, include_portal: bool) -> dict:
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
        record = {"portal": job.source, **record}
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


def write_jobs_file(payload: dict) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = JOBS_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(JOBS_FILE)


def jobs_payload(
    source: str,
    query: str,
    where: str,
    limit: int,
    boards: list[str] | None,
    country: str,
    sort: str,
    posted_within_days: int | None = None,
) -> dict:
    """Fetch jobs for the web app: the same data the terminal prints."""
    sources = selected_sources(source)
    sort_specs = parse_sort(sort)
    results = run_sources(
        sources,
        query,
        where,
        limit,
        boards,
        country,
        open_browser=False,
        posted_within_days=posted_within_days,
    )

    jobs: list[Job] = []
    notes: list[dict] = []
    credits: list[str] = []
    linkedin_url = ""
    for connector, portal_jobs in results:
        jobs.extend(portal_jobs)
        credit = CREDITS.get(connector.key)
        if credit and portal_jobs:
            credits.append(credit)
        for warning in connector.warnings:
            notes.append({"portal": connector.label, "message": warning})
        if connector.key == "linkedin":
            linkedin_url = getattr(connector, "search_url", "")

    ordered = sort_jobs(jobs, sort_specs)
    return {
        "source": source,
        "query": query,
        "where": where,
        "limit": limit,
        "count": len(ordered),
        "jobs": [job_record(job, include_portal=True) for job in ordered],
        "portals": [{"key": cls.key, "label": cls.label} for cls in CONNECTORS],
        "credits": credits,
        "notes": notes,
        "linkedinSearchUrl": linkedin_url,
        "windowDays": posted_within_days or 0,
    }


def _snapshot_current(saved: dict) -> bool:
    return saved.get("windowDays") == WINDOW_DAYS and not saved.get("loading")


def _portal_list() -> list[dict]:
    return [{"key": cls.key, "label": cls.label} for cls in CONNECTORS]


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
        "linkedinSearchUrl": _progress["linkedin"],
        "windowDays": WINDOW_DAYS,
        "loading": loading,
        "cached": cached,
        "fetchedAt": "" if loading else _progress["fetchedAt"],
        "error": _progress["error"],
    }


def _remember(generation: int, connector, batch: list[Job]) -> None:
    """Add a portal's latest jobs. Same link replaces the earlier card (Greenhouse fills the description in a second pass)."""
    with _jobs_lock:
        if generation != _progress["generation"]:
            return
        for job in batch:
            record = job_record(job, include_portal=True)
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
            _progress["notes"].append({"portal": connector.label, "message": warning})
        if connector.key == "linkedin":
            _progress["linkedin"] = getattr(connector, "search_url", "") or ""
        now = time.monotonic()
        if batch and now - _progress.get("last_write", 0.0) >= 0.6:
            write_jobs_file(_payload_from_progress(loading=True))
            _progress["last_write"] = now


def _finish_fetch(generation: int, error: str = "") -> None:
    with _jobs_lock:
        if generation != _progress["generation"]:
            return
        _progress["running"] = False
        _progress["error"] = error
        _progress["fetchedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if error:
            _progress["notes"].append({"portal": "fetch", "message": error})
        payload = _payload_from_progress(loading=False)
        write_jobs_file(payload)


def _fetch_worker(country: str, generation: int) -> None:
    try:
        run_sources(
            list(CONNECTORS),
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
    _progress["linkedin"] = ""
    _progress["error"] = ""
    _progress["fetchedAt"] = ""
    _progress["last_write"] = 0.0


def saved_or_live_jobs(country: str, refresh: bool) -> dict:
    """Return the saved file when it is complete. A new fetch returns jobs as each company comes in."""
    with _jobs_lock:
        if _progress["running"] and not refresh:
            return _payload_from_progress(loading=True)
        if not refresh and not _progress["running"]:
            saved = read_jobs_file()
            if saved is not None and _snapshot_current(saved):
                saved["cached"] = True
                saved["loading"] = False
                return saved
        if _progress["running"]:
            return _payload_from_progress(loading=True)
        _reset_progress()
        generation = _progress["generation"]
        threading.Thread(
            target=_fetch_worker,
            args=(country, generation),
            name="jobs-fetch",
            daemon=True,
        ).start()
        return _payload_from_progress(loading=True)


class JobsApiHandler(BaseHTTPRequestHandler):
    """Read-only JSON API for the web app."""

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
        if route.path == "/api/portals":
            self._send_json(200, {"portals": [{"key": cls.key, "label": cls.label} for cls in CONNECTORS]})
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
            self._send_json(502, {"error": str(exc)})
            return
        self._send_json(200, payload)

    def log_message(self, fmt: str, *args) -> None:
        print(f"  {self.address_string()} {fmt % args}")

    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)


def serve(port: int, country: str) -> None:
    handler = type("JobsApiHandler", (JobsApiHandler,), {"country": country})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"fetchJobsForMe API on http://127.0.0.1:{port}")
    print(f"  GET http://127.0.0.1:{port}/api/jobs?source=all&query=engineer")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
