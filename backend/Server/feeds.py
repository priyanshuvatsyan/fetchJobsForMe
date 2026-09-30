"""Shared persistence and background workers for independently stored feeds."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from Server.api import Job, is_tech_role, within_days
from Server.control import held, stale, token as current_token

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def job_record(job: Job) -> dict:
    return {
        "portal": job.source,
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


class SidecarStore:
    """Atomically maintain one portal's incrementally growing JSON list."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.path = DATA_DIR / f"{key}_jobs.json"
        self._lock = threading.Lock()
        self._records: list[dict] = []
        self._last_write = 0.0
        self.epoch = 0

    def reset(self) -> int:
        with self._lock:
            self.epoch += 1
            self._records = []
            self._write()
            self._last_write = time.monotonic()
            return self.epoch

    def append(self, job: Job, epoch: int | None = None) -> None:
        with self._lock:
            if epoch is not None and epoch != self.epoch:
                return
            self._records.append(job_record(job))
            now = time.monotonic()
            if now - self._last_write >= 0.5:
                self._write()
                self._last_write = now

    def flush(self) -> None:
        with self._lock:
            self._write()
            self._last_write = time.monotonic()

    def read(self) -> list[dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [
            record
            for record in payload
            if isinstance(record, dict) and is_tech_role(record.get("role", ""))
        ]

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(self._records, indent=4, ensure_ascii=False)
        temporary = self.path.with_suffix(".json.tmp")
        for attempt in range(5):
            try:
                temporary.write_text(body, encoding="utf-8")
                temporary.replace(self.path)
                return
            except OSError:
                time.sleep(0.3 * (attempt + 1))
        try:
            self.path.write_text(body, encoding="utf-8")
        except OSError as exc:
            print(f"could not save {self.path.name}: {exc}")


_stores: dict[str, SidecarStore] = {}
_stores_lock = threading.Lock()


def get_store(key: str) -> SidecarStore:
    with _stores_lock:
        if key not in _stores:
            _stores[key] = SidecarStore(key)
        return _stores[key]


class SidecarConnector:
    """Base class for a public feed normalized into the shared Job model."""

    persist = "sidecar"

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def iter_items(self, query: str, posted_within_days: int | None):
        raise NotImplementedError

    def parse_item(self, item: dict) -> Job | None:
        raise NotImplementedError

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 0,
        boards: list[str] | None = None,
        on_batch=None,
        posted_within_days: int | None = None,
    ) -> list[Job]:
        del boards
        store = get_store(self.key)
        started = current_token()
        epoch = store.reset()
        jobs: list[Job] = []
        seen: set[str] = set()
        cap = None if limit <= 0 else limit
        location_query = where.strip().casefold()
        try:
            items = self.iter_items(query.strip(), posted_within_days)
            for item in items:
                if stale(started) or (cap is not None and len(jobs) >= cap):
                    break
                try:
                    job = self.parse_item(item)
                except (KeyError, TypeError, ValueError) as exc:
                    print(f"{self.label}: skipped malformed listing: {exc}")
                    continue
                if job is None or not job.url or job.url in seen:
                    continue
                seen.add(job.url)
                if not is_tech_role(job.title):
                    continue
                if (
                    posted_within_days
                    and job.posted_at
                    and not within_days(job.posted_at, posted_within_days)
                ):
                    continue
                if location_query and location_query not in (
                    f"{job.title} {job.company} {job.location}".casefold()
                ):
                    continue
                jobs.append(job)
                store.append(job, epoch)
                if on_batch is not None:
                    on_batch([job])
                print(f"{self.label} [{len(jobs)}] {job.title} — {job.company}")
        except Exception as exc:
            self.warnings.append(str(exc))
            print(f"{self.label} fetch failed: {exc}")
        finally:
            if store.epoch == epoch:
                store.flush()
        return jobs


class FeedCoordinator:
    """Start sidecar connectors once and expose their combined live state."""

    def __init__(
        self,
        connectors: list[type],
        window_days: int,
        paused: set[str] | None = None,
    ) -> None:
        self.connectors = {connector.key: connector for connector in connectors}
        self.window_days = window_days
        self.paused = set(paused or ())
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._run_tokens: dict[str, int] = {}
        self._warnings: dict[str, list[str]] = {}
        self._timings: dict[str, float] = {}
        self.suppressed = False

    def start_all(self, refresh: bool) -> None:
        for key in self.connectors:
            self.start(key, refresh)

    def start(self, key: str, refresh: bool) -> None:
        connector_class = self.connectors.get(key)
        if connector_class is None or key in self.paused:
            return
        if not refresh and (self.suppressed or held()):
            return
        run_token = current_token()
        with self._lock:
            if self._running and self._run_tokens.get(key) == run_token and key in self._running:
                return
            if not refresh and get_store(key).read():
                return
            self._running.add(key)
            self._run_tokens[key] = run_token
        threading.Thread(
            target=self._worker,
            args=(connector_class, run_token),
            name=f"{key}-fetch",
            daemon=True,
        ).start()

    def stop(self) -> None:
        """Drop the loading flags and flush JSON already collected. Threads exit on their own."""
        self.suppressed = True
        with self._lock:
            self._running.clear()
        for key in self.connectors:
            get_store(key).flush()

    def _worker(self, connector_class: type, run_token: int) -> None:
        connector = connector_class()
        key = connector_class.key
        started = time.perf_counter()
        try:
            kwargs = {"limit": 0, "posted_within_days": self.window_days}
            if key == "linkedin":
                kwargs["open_browser"] = False
            connector.fetch(**kwargs)
            if current_token() == run_token:
                get_store(key).flush()
            self._warnings[key] = list(connector.warnings)
        except Exception as exc:
            self._warnings[key] = [str(exc)]
            print(f"{connector_class.label} fetch failed: {exc}")
        finally:
            self._timings[key] = round(time.perf_counter() - started, 1)
            with self._lock:
                if self._run_tokens.get(key) == run_token:
                    self._running.discard(key)

    def payload(self, key: str) -> dict:
        jobs = get_store(key).read()
        with self._lock:
            loading = key in self._running
        return {"jobs": jobs, "count": len(jobs), "loading": loading}

    def merge(self, payload: dict, credits: dict[str, str]) -> dict:
        result = dict(payload)
        jobs: list[dict] = []
        seen: set[str] = set()
        for record in payload.get("jobs") or []:
            link = record.get("link") or ""
            key = link or f"{record.get('portal')}:{record.get('company')}:{record.get('role')}"
            if key in seen:
                continue
            seen.add(key)
            jobs.append(record)
        for key in self.connectors:
            for record in get_store(key).read():
                link = record.get("link") or ""
                identity = link or f"{record.get('portal')}:{record.get('company')}:{record.get('role')}"
                if identity in seen:
                    continue
                seen.add(identity)
                jobs.append(record)
        with self._lock:
            running = bool(self._running)
            running_keys = set(self._running)
        result["jobs"] = jobs
        result["count"] = len(jobs)
        result["loading"] = bool(payload.get("loading")) or running
        result["feedLoading"] = sorted(running_keys)
        merged_credits = list(payload.get("credits") or [])
        for key in self.connectors:
            credit = credits.get(key)
            if credit and get_store(key).read() and credit not in merged_credits:
                merged_credits.append(credit)
        result["credits"] = merged_credits
        notes = list(payload.get("notes") or [])
        for key, warnings in self._warnings.items():
            label = self.connectors[key].label
            notes.extend({"portal": label, "message": warning} for warning in warnings)
        result["notes"] = notes
        return result
