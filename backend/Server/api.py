"""HTTP client and public job-board endpoints."""

from __future__ import annotations

import hashlib
import html
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, CancelledError, ThreadPoolExecutor, wait
from pathlib import Path
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from Server.control import cancelled, token

USER_AGENT = "fetchJobsForMe/0.1 (personal job search; public APIs only)"
# RemoteOK's public JSON API redirect-loops unless the client sends a browser User-Agent.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_SECRET_PARAMS = {"app_key", "app_id", "api_key", "apikey"}
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
CACHE_TTL_SECONDS = 2 * 60 * 60

GREENHOUSE_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
GREENHOUSE_JOB_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
LEVER_POSTINGS_URL = "https://api.lever.co/v0/postings/{site}"
_LEVER_PAGE = 100
ASHBY_BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"
REMOTIVE_JOBS_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_JOBS_URL = "https://remoteok.com/api"
ARBEITNOW_JOBS_URL = "https://www.arbeitnow.com/api/job-board-api"
ADZUNA_SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"



class ApiError(Exception):
    def __init__(self, url: str, status: int | str, message: str) -> None:
        self.url = redact_url(url)
        self.status = status
        super().__init__(f"{status} {self.url}: {message}")


@dataclass(frozen=True)
class Job:
    source: str
    title: str
    company: str
    location: str
    url: str
    posted_at: str = ""
    experience: str = ""
    skill: str = ""
    salary: str = ""
    about_company: str = ""
    job_description: str = ""
    openings: str = ""
    applicants: str = ""
    apply_url: str = ""
    posted_by: str = ""
    poster_email: str = ""


def apply_url_from_html(html: str, page_url: str = "") -> str:
    """Company or portal apply link from a job page. Empty when the page has no separate apply link."""
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    page = urljoin(page_url, page_url).split("#")[0].rstrip("/") if page_url else ""
    found = ""
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url or "", anchor.get("href") or "").split("#")[0].strip()
        if not href.startswith(("http://", "https://")):
            continue
        label = " ".join(
            part
            for part in (
                clean(anchor.get_text(" ", strip=True)),
                clean(anchor.get("aria-label")),
                clean(anchor.get("id")),
                clean(anchor.get("title")),
                " ".join(anchor.get("class") or []),
            )
            if part
        ).casefold()
        target = href.casefold()
        if any(word in target for word in ("login", "signin", "sign-in", "signup", "accounts.google")):
            continue
        if "apply" not in label and "apply" not in target:
            continue
        if page and href.rstrip("/") == page:
            continue
        found = href
        if label.startswith("apply"):
            return href
    return found


_YEARS = re.compile(
    r"(\d{1,2}\s*(?:\+|plus)?(?:\s*(?:-|–|to)\s*\d{1,2}\s*(?:\+|plus)?)?\s*years?)",
    re.I,
)
_DEGREE = re.compile(r"((?:bachelor|master|ph\.?d|mba)(?:['’]s)?(?:\s+degree)?)", re.I)
_LEVEL = re.compile(r"\b(intern|junior|senior|staff|principal|lead|director|head)\b", re.I)


_board_client: ApiClient | None = None


def get_board_client() -> ApiClient:
    """Shorter timeout for company-board calls. A missing board should fail fast."""
    global _board_client
    if _board_client is None:
        _board_client = ApiClient(timeout=12)
    return _board_client


class ApiClient:
    def __init__(self, user_agent: str = USER_AGENT, timeout: float = 60) -> None:
        self.user_agent = user_agent
        self.timeout = timeout

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        user_agent: str | None = None,
        retries: int = 2,
    ):
        target = with_query(url, params)
        cached = read_cache(target)
        if cached is not None:
            return cached
        last_error: ApiError | None = None
        attempts = max(1, retries)
        for attempt in range(attempts):
            try:
                payload = self._read_json(url, params, user_agent)
            except ApiError as exc:
                last_error = exc
                if attempt == attempts - 1 or not _retryable(exc):
                    raise
                time.sleep(0.4 * (attempt + 1))
                continue
            write_cache(target, payload)
            return payload
        raise last_error  # pragma: no cover

    def _read_json(self, url: str, params: dict | None, user_agent: str | None):
        target = with_query(url, params)
        request = urllib.request.Request(
            target,
            headers={
                "User-Agent": user_agent or self.user_agent,
                "Accept": "application/json",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = _error_detail(exc.read())
            raise ApiError(target, exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise ApiError(target, "connection", str(exc.reason)) from exc
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            # WinError 10054 is raised while reading the body, not as URLError.
            raise ApiError(target, "connection", str(exc)) from exc

        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(target, status, "response was not JSON") from exc


def get_client() -> ApiClient:
    return ApiClient()


def _retryable(exc: ApiError) -> bool:
    return exc.status == "connection" or exc.status in {429, 500, 502, 503, 504}


def with_query(url: str, params: dict | None) -> str:
    if not params:
        return url
    query = urllib.parse.urlencode(
        {key: value for key, value in params.items() if value is not None and value != ""}
    )
    if not query:
        return url
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{query}"


def redact_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    safe = [
        (key, "***" if key.lower() in _SECRET_PARAMS else value)
        for key, value in pairs
    ]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(safe)))


def clean(value) -> str:
    return " ".join(str(value or "").split())


_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_LABELED_EMAIL = re.compile(
    r"(?:e-?mail|contact)\s*[:\-]\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
    re.I,
)
_POSTED_BY = re.compile(
    r"(?:posted by|job poster|recruiter|hiring manager)\s*[:\-]?\s*([A-Z][A-Za-z .'\-]{1,80})",
    re.I,
)
_OPENINGS = re.compile(r"(?:openings?|vacancies)\s*[:\-]?\s*(\d+\+?)", re.I)
_OPENINGS_TAIL = re.compile(r"(\d+\+?)\s+(?:openings?|vacancies)\b", re.I)
_APPLICANTS = re.compile(r"(?:applicants?|applications?)\s*[:\-]?\s*(\d+\+?)", re.I)
_APPLICANTS_TAIL = re.compile(r"(\d+\+?)\s+applicants?\b", re.I)
_SKIP_EMAIL = ("noreply", "no-reply", "privacy@", "support@", "help@", "example.com")


def _usable_email(value: str) -> str:
    email = clean(value).strip(".,;:()<>")
    if not _EMAIL.fullmatch(email):
        return ""
    folded = email.casefold()
    if any(marker in folded for marker in _SKIP_EMAIL):
        return ""
    return email


def _contact_name(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("name") or ""
    name = clean(value)
    if not name or "@" in name or len(name) > 80:
        return ""
    return name


def posting_facts(posting: dict | None = None, text: str = "") -> dict:
    """Poster, email, openings, and applicants only when a portal publishes them."""
    posting = posting or {}
    contact = posting.get("applicationContact") or {}
    if isinstance(contact, list):
        contact = contact[0] if contact else {}
    if not isinstance(contact, dict):
        contact = {}
    posted_by = _contact_name(contact)
    email = _usable_email(contact.get("email") or "")
    openings = clean(posting.get("totalJobOpenings"))
    applicants = ""
    source = text or ""
    if not posted_by:
        match = _POSTED_BY.search(source)
        posted_by = clean(match.group(1)).rstrip(".,;") if match else ""
    if not email:
        match = _LABELED_EMAIL.search(source)
        email = _usable_email(match.group(1)) if match else ""
    if not email:
        mailto = re.search(r"mailto:([^\"'\s>]+)", source, re.I)
        email = _usable_email(mailto.group(1)) if mailto else ""
    if not openings:
        match = _OPENINGS.search(source) or _OPENINGS_TAIL.search(source)
        openings = clean(match.group(1)) if match else ""
    if not applicants:
        match = _APPLICANTS.search(source) or _APPLICANTS_TAIL.search(source)
        applicants = clean(match.group(1)) if match else ""
    return {
        "posted_by": posted_by,
        "email": email,
        "openings": openings,
        "applicants": applicants,
    }


def poster_from_html(html: str) -> str:
    """Name next to a public 'Job poster' or 'Posted by' label."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all(string=re.compile(r"job poster|posted by", re.I)):
        container = node.parent
        for _ in range(3):
            if container is None:
                break
            block = container.get_text("\n", strip=True)
            if len(block) <= 180:
                found = posting_facts({}, block)["posted_by"]
                if found:
                    return found
            container = container.parent
    return ""


def apply_posting_facts(job: Job) -> Job:
    """Fill empty poster and count fields from text the portal already returned."""
    facts = posting_facts({}, f"{job.about_company}\n{job.job_description}")
    return replace(
        job,
        posted_by=job.posted_by or facts["posted_by"],
        poster_email=job.poster_email or facts["email"],
        openings=job.openings or facts["openings"],
        applicants=job.applicants or facts["applicants"],
    )


# Web fetches keep CSE/IT jobs from this window: India, Indian hybrid, or remote.
POSTED_WINDOW_DAYS = 15

_INDIA_MARKERS = (
    "india",
    "andhra pradesh",
    "arunachal",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "delhi",
    "chandigarh",
    "puducherry",
    "jammu",
    "kashmir",
    "ladakh",
    "bengaluru",
    "bangalore",
    "hyderabad",
    "mumbai",
    "pune",
    "chennai",
    "noida",
    "gurgaon",
    "gurugram",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "thiruvananthapuram",
    "indore",
    "lucknow",
    "nagpur",
    "coimbatore",
    "vadodara",
    "surat",
    "bhopal",
    "visakhapatnam",
    "mysuru",
    "mysore",
    "kanpur",
    "nashik",
    "faridabad",
    "ghaziabad",
    "ncr",
    "pimpri",
    "chinchwad",
    "thane",
    "navi mumbai",
    "mohali",
    "panchkula",
    "zirakpur",
    "mangalore",
    "mangaluru",
    "trivandrum",
    "cochin",
    "calicut",
    "kozhikode",
    "ernakulam",
    "kannur",
    "kottayam",
    "palakkad",
    "kollam",
    "madurai",
    "coimbatore",
    "salem",
    "tiruppur",
    "vellore",
    "erode",
    "dindigul",
    "tiruchirappalli",
    "trichy",
    "amravati",
    "raipur",
    "bhubaneswar",
    "bhubaneshwar",
    "kolhapur",
    "vijayawada",
    "ludhiana",
    "solapur",
    "gandhinagar",
    "nellore",
    "panaji",
    "panjim",
    "dehradun",
    "udaipur",
    "guwahati",
    "varanasi",
    "dharwad",
    "rohtak",
    "vapi",
    "vijayapura",
    "tirupati",
    "rajkot",
    "bikaner",
    "karnal",
    "kota",
    "meerut",
    "jamshedpur",
    "guntur",
    "srikakulam",
    "kadapa",
    "vasai",
    "jabalpur",
    "nagercoil",
    "siliguri",
    "jodhpur",
    "roorkee",
    "vizianagaram",
    "vishakhapatnam",
    "ajmer",
    "solan",
    "bareilly",
    "kurnool",
    "aligarh",
    "bhavnagar",
    "malappuram",
    "baddi",
    "patna",
    "ranchi",
    "jalandhar",
    "amritsar",
    "agra",
    "prayagraj",
    "allahabad",
    "aurangabad",
    "hubli",
    "hubballi",
    "belgaum",
    "belagavi",
    "warangal",
    "pondicherry",
    "cuttack",
    "rourkela",
    "howrah",
    "durgapur",
    "gwalior",
    "ujjain",
    "haridwar",
    "shimla",
    "patiala",
    "ambala",
    "panipat",
    "sonipat",
    "manesar",
    "secunderabad",
    "gachibowli",
    "madhapur",
    "kondapur",
    "hinjewadi",
    "whitefield",
    "bombay",
    "madras",
    "calcutta",
    "baroda",
    "poona",
)
# A bare "Salem" on Indian boards is Salem, Tamil Nadu. The same word in a US address is not.
_AMBIGUOUS_INDIA = {"salem"}
_FOREIGN_COUNTRY = (
    "united states",
    "united kingdom",
    "u.s.a",
    "usa",
    "canada",
    "australia",
    "germany",
    "france",
    "ireland",
    "singapore",
)
_REMOTE_MARKERS = ("remote", "work from home", "wfh", "anywhere", "worldwide")


def _mentions(text: str, marker: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text) is not None


def in_india(location: str) -> bool:
    """True when the text names India or an Indian city, even without the word India."""
    text = (location or "").casefold()
    hits = [marker for marker in _INDIA_MARKERS if _mentions(text, marker)]
    if not hits:
        return False
    if any(marker not in _AMBIGUOUS_INDIA for marker in hits):
        return True
    return not any(country in text for country in _FOREIGN_COUNTRY)


def keeps_india_hybrid_or_remote(location: str) -> bool:
    """India (including Indian hybrid) or a remote role anywhere."""
    text = (location or "").casefold()
    if not text:
        return False
    if any(_mentions(text, marker) for marker in _REMOTE_MARKERS):
        return True
    return in_india(text)


def visible_record(record: dict, window_days: int = POSTED_WINDOW_DAYS) -> bool:
    """Saved rows shown on the jobs page: tech, India/hybrid/remote, inside the window."""
    if not isinstance(record, dict) or not is_tech_role(record.get("role", "")):
        return False
    if not keeps_india_hybrid_or_remote(record.get("location") or ""):
        return False
    posted = record.get("added on") or ""
    if posted and window_days and not within_days(posted, window_days):
        return False
    return True


def within_days(posted_at: str, days: int) -> bool:
    """True when a portal timestamp falls inside the last `days` days."""
    if not posted_at or days <= 0:
        return False
    try:
        moment = datetime.strptime(posted_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - moment <= timedelta(days=days)


_GMT_OFFSET = re.compile(r"\sGMT([+-])(\d{2}):?(\d{2})?$", re.I)
_COMPACT_OFFSET = re.compile(r"([+-])(\d{2})(\d{2})$")


def _with_iso_offset(text: str) -> str:
    """Turn 'GMT+0530' and '+0530' into an offset fromisoformat understands."""
    gmt = _GMT_OFFSET.search(text)
    if gmt:
        sign, hours, minutes = gmt.group(1), gmt.group(2), gmt.group(3) or "00"
        text = f"{text[: gmt.start()]}{sign}{hours}:{minutes}"
    compact = _COMPACT_OFFSET.search(text)
    if compact and (compact.start() == 0 or text[compact.start() - 1] != ":"):
        sign, hours, minutes = compact.group(1), compact.group(2), compact.group(3)
        text = f"{text[: compact.start()]}{sign}{hours}:{minutes}"
    return text


def to_datetime(value) -> str:
    """Portal create time as UTC 'YYYY-MM-DD HH:MM:SS'."""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        try:
            moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return ""
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    text = _with_iso_offset(str(value).strip())
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        if len(text) >= 19 and text[4] == "-" and text[10] in " T":
            return text[:10] + " " + text[11:19]
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return text[:10] + " 00:00:00"
        return ""
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def to_date(value) -> str:
    stamped = to_datetime(value)
    return stamped[:10] if stamped else ""


def company_from_slug(slug: str) -> str:
    return clean(slug).replace("-", " ").replace("_", " ").title()


_TECH_ROLE = re.compile(
    r"\b(?:"
    r"software|developer|programmer|coder|full[\s-]?stack|front[\s-]?end|back[\s-]?end|"
    r"web|mobile|android|ios|devops|devsecops|mlops|llmops|dataops|sre|site reliability|"
    r"cloud|infrastructure|sysadmin|system administrator|systems? engineer|systems? analyst|"
    r"network|cyber|cybersecurity|infosec|information security|application security|"
    r"security engineer|security analyst|penetration|pentest|soc analyst|"
    r"data|analytics|business intelligence|bi|etl|big data|"
    r"machine learning|ml|ai|artificial intelligence|deep learning|nlp|computer vision|"
    r"llm|gen\s?ai|generative|prompt engineer|"
    r"automation|rpa|qa|quality assurance|sdet|tester|testing|test engineer|"
    r"database|dba|sql|python|java|javascript|typescript|react|angular|node(?:\.?js)?|"
    r"\.net|golang|rust|php|ruby|scala|kotlin|swift|salesforce|servicenow|sap|erp|"
    r"blockchain|web3|embedded|firmware|game developer|ui developer|ux engineer|"
    r"(?:software|solutions?|cloud|data|enterprise|technical|systems?|security|it) architect|"
    r"tech lead|technical lead|cto|kubernetes|platform|"
    r"application support|technical support|it support|helpdesk|help desk"
    r")\b",
    re.I,
)
_IT_WORD = re.compile(r"\bIT\b")
_ENGINEER = re.compile(r"\bengineer(?:ing)?\b", re.I)
_NOT_TECH = re.compile(
    r"\b(?:civil|mechanical|chemical|structural|construction|hvac|plumbing|geotechnical|"
    r"environmental|petroleum|mining|manufacturing|maintenance|field service|"
    r"sales engineer|data entry|security guard|security officer|process engineer|"
    r"electrical engineer|electronics engineer|production engineer|biomedical|"
    r"agricultural|marine|non[- ]?it|recruiter|business development)\b",
    re.I,
)


def is_tech_role(title: str) -> bool:
    """Computer science and IT roles only. Uses the job title."""
    text = clean(title)
    if not text or _NOT_TECH.search(text):
        return False
    if _TECH_ROLE.search(text) or _IT_WORD.search(text):
        return True
    return bool(_ENGINEER.search(text))


def job_matches(job: Job, query: str, where: str) -> bool:
    if not is_tech_role(job.title):
        return False
    haystack = f"{job.title} {job.company} {job.location}".casefold()
    if query and query.casefold() not in haystack:
        return False
    if where and where.casefold() not in haystack:
        return False
    return True


def plain_text(value: str) -> str:
    text = html.unescape(html.unescape(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return clean(text)


_JOB_HEADING = re.compile(
    r"^(?:"
    r"what you'll (?:do|be doing|bring|need)|"
    r"what you will do|"
    r"(?:your |key |core |the )?responsibilities|"
    r"about (?:the |this )?role|"
    r"(?:the )?role(?: overview)?|"
    r"job (?:description|summary|duties)|"
    r"(?:brief )?description of (?:the )?duties|"
    r"(?:minimum |preferred |basic |required )?qualifications|"
    r"requirements|"
    r"who you are|"
    r"about you|"
    r"in this role|"
    r"a day in the life|"
    r"duties|"
    r"what we're looking for|"
    r"benefits"
    r")$",
    re.I,
)
_ROLE_START = re.compile(
    r"^(?:"
    r"(?:we're|we are)\s+(?:looking for|seeking|hiring)\b|"
    r"in this role\b|"
    r"you will be responsible\b|"
    r"as (?:a|an) (?!small\b|team\b|company\b|whole\b|result\b)"
    r")",
    re.I,
)
_GLUED_JOB = re.compile(
    r"^(?:your (?:mission|tasks|profile|role)|in this role|what you'll do|responsibilities)\b",
    re.I,
)
_ABOUT_HEADING = re.compile(
    r"^(?:about (?:the |our )?company|about us|who we are|our story|company overview)$",
    re.I,
)
_GLUED_ABOUT = re.compile(r"^(?:about us|about the company|about our company|who we are)\b", re.I)
_NAMED_ABOUT = re.compile(
    r"^about (?!the role\b)(?!this role\b)(?!you\b)(?!the job\b)(?!the position\b)\S.{0,40}$",
    re.I,
)
_COMPANYISH = re.compile(
    r"\b(?:our mission|our company|our team|our platform|we are|we're|founded|"
    r"headquartered|is an? |helps |helping )\b",
    re.I,
)
_ALREADY_ROLE = re.compile(r"^(?:job title\b|reports to\b|this (?:is|role)\b)", re.I)
_INTRO_DIV = re.compile(
    r'<div[^>]*class="[^"]*content-intro[^"]*"[^>]*>(.*?)</div>',
    re.I | re.S,
)


def _norm(value: str) -> str:
    return value.replace("’", "'").replace("‘", "'").replace("`", "'")


def _html_lines(value: str) -> str:
    text = html.unescape(html.unescape(value or ""))
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</\s*(?:p|div|h[1-6]|li|tr|ul|ol)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _heading(line: str) -> str:
    return _norm(line).lstrip("- ").strip().rstrip(":").strip()


def _is_about_line(line: str) -> bool:
    label = _heading(line)
    return bool(_ABOUT_HEADING.match(label) or _GLUED_ABOUT.match(label) or _NAMED_ABOUT.match(label))


def _is_job_line(line: str) -> bool:
    label = _heading(line)
    stripped = _norm(line.strip())
    return bool(_JOB_HEADING.match(label) or _ROLE_START.match(stripped) or _GLUED_JOB.match(stripped))


def _split_plain(text: str) -> tuple[str, str]:
    """Separate a company intro from the role when the posting marks the change."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "", ""
    about_at = [index for index, line in enumerate(lines) if _is_about_line(line)]
    job_at = next((index for index, line in enumerate(lines) if _is_job_line(line)), None)
    consumed: set[int] = set()
    about_chunks: list[str] = []

    for start in about_at:
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if index != start and (_is_job_line(lines[index]) or _is_about_line(lines[index])):
                end = index
                break
        consumed.update(range(start, end))
        about_chunks.append("\n".join(lines[start:end]).strip())

    if job_at and job_at > 0:
        prefix = "\n".join(lines[:job_at]).strip()
        folded = _norm(prefix)
        if len(prefix) >= 60 and not _ALREADY_ROLE.match(folded) and _COMPANYISH.search(folded):
            consumed.update(range(job_at))
            if not any(index < job_at for index in about_at):
                about_chunks.insert(0, prefix)

    about = "\n\n".join(chunk for chunk in about_chunks if chunk)
    role = "\n".join(line for index, line in enumerate(lines) if index not in consumed).strip()
    if not about or not role:
        return "", text.strip()
    return about, role


def split_description(body: str, *job_sections: str) -> tuple[str, str]:
    """Split a posting into about-company text and the job description."""
    raw = html.unescape(html.unescape(body or ""))
    intro_html = ""
    match = _INTRO_DIV.search(raw)
    if match:
        intro_html = match.group(1)
        raw = raw[: match.start()] + raw[match.end() :]
    intro = _html_lines(intro_html)
    rest = _html_lines(raw)
    about, role = _split_plain(rest)
    if intro:
        about = "\n\n".join(part for part in (intro, about) if part)
        if not role:
            role = rest
    sections = [_html_lines(part) for part in job_sections if part and str(part).strip()]
    narrative_is_company = (
        not about
        and rest
        and not any(_is_job_line(line) for line in rest.splitlines())
        and _COMPANYISH.search(_norm(rest))
        and not _ALREADY_ROLE.match(_norm(rest))
    )
    if sections and narrative_is_company:
        about, role = rest, ""
    if sections:
        role = "\n\n".join(part for part in (role, *sections) if part)
    if about and not role:
        role, about = about, ""
    return about.strip(), role.strip()


def format_skills(values) -> str:
    """Join skill or tag values supplied by a job portal. No fixed vocabulary."""
    if values is None:
        return ""
    if isinstance(values, str):
        values = [values]
    elif isinstance(values, dict):
        values = [values.get("name") or values.get("label") or ""]
    found: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, dict):
            item = item.get("name") or item.get("label") or item.get("skill") or ""
        text = clean(item)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        found.append(text)
    return ", ".join(found)


def extract_experience(title: str, body: str = "") -> str:
    description = plain_text(body)
    years = _YEARS.search(description)
    if years:
        return clean(years.group(1))
    degree = _DEGREE.search(description)
    if degree:
        return clean(degree.group(1))
    level = _LEVEL.search(title or "")
    if level:
        return level.group(1).title()
    return ""


def job_profile(title: str, body: str = "", skills=None) -> tuple[str, str]:
    return extract_experience(title, body), format_skills(skills)


_SALARY = re.compile(
    r"((?:[$£€₹]|USD|EUR|GBP|INR|CAD|AUD)\s?\d[\d,]*(?:\.\d+)?\s*[kK]?"
    r"(?:\s*(?:-|–|to)\s*(?:[$£€₹]|USD|EUR|GBP|INR|CAD|AUD)?\s?\d[\d,]*(?:\.\d+)?\s*[kK]?)?)",
    re.I,
)


def money_span(low, high, currency: str = "$") -> str:
    def amount(value) -> int:
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return 0
        return number if number > 0 else 0

    start, end = amount(low), amount(high)
    if start and end and start != end:
        return f"{currency}{start:,} - {currency}{end:,}"
    if start or end:
        return f"{currency}{(start or end):,}"
    return ""


def extract_salary(body: str = "", explicit: str = "") -> str:
    stated = clean(explicit)
    if stated and stated.casefold() not in {"n/a", "na", "none", "not specified", "null"}:
        return stated
    match = _SALARY.search(plain_text(body))
    return clean(match.group(1)) if match else ""


def is_missing_board(exc: Exception) -> bool:
    return isinstance(exc, ApiError) and exc.status == 404


def read_cache(url: str):
    path = _cache_path(url)
    try:
        if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(url: str, payload) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def load_boards(tokens: list[str], fetch, workers: int = 12, accept=None):
    """Fetch company boards until accept() says there are enough jobs.

    A 404 means the company is not on that portal and is skipped.
    Boards that have not been started are not requested.
    """
    found: list[tuple[str, object]] = []
    warnings: list[str] = []
    pending_tokens = list(tokens)
    if not pending_tokens:
        return found, warnings

    started = token()
    stop = False

    def halt() -> bool:
        return stop or cancelled() or token() != started
    index = 0
    inflight: dict = {}
    worker_count = min(max(1, workers), len(pending_tokens))

    def submit_more(pool: ThreadPoolExecutor) -> None:
        nonlocal index
        while index < len(pending_tokens) and len(inflight) < worker_count and not halt():
            board = pending_tokens[index]
            index += 1
            inflight[pool.submit(fetch, board)] = board

    def take(future) -> None:
        nonlocal stop
        board = inflight.pop(future)
        try:
            payload = future.result()
        except CancelledError:
            return
        except ApiError as exc:
            if not is_missing_board(exc):
                warnings.append(f"{board}: {exc}")
            return
        except (ValueError, OSError) as exc:
            warnings.append(f"{board}: {exc}")
            return
        found.append((board, payload))
        if accept is not None and accept(board, payload):
            stop = True

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        submit_more(pool)
        while inflight:
            done, _pending = wait(inflight, return_when=FIRST_COMPLETED)
            for future in done:
                take(future)
            if halt():
                for future in inflight:
                    future.cancel()
                while inflight:
                    done, _pending = wait(inflight, return_when=FIRST_COMPLETED)
                    for future in done:
                        take(future)
                break
            submit_more(pool)
    return found, warnings


def select_jobs(jobs: list[Job], query: str, where: str, limit: int) -> list[Job]:
    matched = [job for job in jobs if job.title and job.url and job_matches(job, query, where)]
    matched.sort(key=lambda job: (bool(job.posted_at), job.posted_at), reverse=True)
    if limit <= 0 or len(matched) <= limit:
        return matched
    by_company: dict[str, list[Job]] = {}
    order: list[str] = []
    for job in matched:
        key = job.company.casefold() or job.title.casefold()
        if key not in by_company:
            order.append(key)
            by_company[key] = []
        by_company[key].append(job)
    if len(order) == 1:
        return matched[:limit]
    picked: list[Job] = []
    while len(picked) < limit:
        progressed = False
        for key in order:
            bucket = by_company[key]
            if not bucket:
                continue
            picked.append(bucket.pop(0))
            progressed = True
            if len(picked) >= limit:
                break
        if not progressed:
            break
    return picked


def valid_token(token: str) -> bool:
    if not token or len(token) > 80:
        return False
    first, rest = token[0], token[1:]
    if not first.isalnum():
        return False
    return all(char.isalnum() or char in "-_" for char in rest)


def _error_detail(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text or text.startswith("<"):
        return "request failed"
    return " ".join(text.split())[:160]


def fetch_greenhouse_board(board: str, client: ApiClient | None = None) -> dict:
    if not valid_token(board):
        raise ValueError(f"invalid Greenhouse board token: {board}")
    http = client or get_board_client()
    return http.get_json(GREENHOUSE_JOBS_URL.format(board=board), retries=3)


def fetch_greenhouse_job(board: str, job_id: int | str, client: ApiClient | None = None) -> dict:
    if not valid_token(board) or not str(job_id).isdigit():
        raise ValueError(f"invalid Greenhouse job: {board}/{job_id}")
    http = client or get_board_client()
    return http.get_json(GREENHOUSE_JOB_URL.format(board=board, job_id=job_id), retries=3)


def fetch_lever_postings(site: str, limit: int = 0, client: ApiClient | None = None) -> list:
    """Every posting on the site. Lever pages in batches; limit only applies to a short CLI fetch."""
    if not valid_token(site):
        raise ValueError(f"invalid Lever site: {site}")
    http = client or ApiClient(timeout=30)
    if limit > 0:
        return _lever_page(http, site, skip=0, limit=limit)
    postings: list = []
    seen: set[str] = set()
    skip = 0
    started = token()
    while skip < 5000:
        if cancelled() or token() != started:
            break
        page = _lever_page(http, site, skip=skip, limit=_LEVER_PAGE)
        fresh = []
        for item in page:
            if not isinstance(item, dict):
                continue
            ident = str(item.get("id") or "")
            if ident and ident in seen:
                continue
            if ident:
                seen.add(ident)
            fresh.append(item)
        postings.extend(fresh)
        if len(page) < _LEVER_PAGE or not fresh:
            break
        skip += len(page)
    return postings


def _lever_page(http: ApiClient, site: str, skip: int, limit: int) -> list:
    params = {"mode": "json", "limit": max(1, min(limit, _LEVER_PAGE))}
    if skip:
        params["skip"] = skip
    payload = http.get_json(LEVER_POSTINGS_URL.format(site=site), params=params, retries=3)
    if not isinstance(payload, list):
        raise ValueError(f"{site}: unexpected Lever response")
    return payload


def fetch_ashby_board(board: str, client: ApiClient | None = None) -> dict:
    if not valid_token(board):
        raise ValueError(f"invalid Ashby board: {board}")
    http = client or get_board_client()
    return http.get_json(ASHBY_BOARD_URL.format(board=board), retries=3)


def fetch_remotive_jobs(query: str = "", limit: int = 0, client: ApiClient | None = None) -> dict:
    http = client or get_client()
    params: dict = {}
    if query:
        params["search"] = query
    if limit > 0:
        params["limit"] = limit
    return http.get_json(REMOTIVE_JOBS_URL, params=params or None)


def fetch_remoteok_jobs(client: ApiClient | None = None) -> list:
    http = client or get_client()
    payload = http.get_json(REMOTEOK_JOBS_URL, user_agent=BROWSER_USER_AGENT)
    if not isinstance(payload, list):
        raise ValueError("unexpected RemoteOK response")
    return payload


def fetch_arbeitnow_jobs(client: ApiClient | None = None) -> dict:
    http = client or get_client()
    return http.get_json(ARBEITNOW_JOBS_URL)


def adzuna_credentials() -> tuple[str, str]:
    return os.environ.get("ADZUNA_APP_ID", "").strip(), os.environ.get("ADZUNA_APP_KEY", "").strip()


def fetch_adzuna_jobs(
    country: str,
    query: str,
    where: str,
    limit: int,
    client: ApiClient | None = None,
) -> dict:
    app_id, app_key = adzuna_credentials()
    if not app_id or not app_key:
        raise ValueError("set ADZUNA_APP_ID and ADZUNA_APP_KEY to call Adzuna")
    http = client or get_client()
    return http.get_json(
        ADZUNA_SEARCH_URL.format(country=country, page=1),
        params={
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": max(1, min(limit, 50) if limit > 0 else 50),
            "what": query,
            "where": where,
            "content-type": "application/json",
        },
    )
