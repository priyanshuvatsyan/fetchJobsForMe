"""Naukri public search pages, read after a normal Chrome window renders them.

A plain HTTP call receives an empty list, and headless Chrome is denied.
Opening the same public search URL in a visible Chrome window returns the
job cards Naukri shows to any visitor. No login, no saved session, and no
attempt to disguise the browser.
"""

from __future__ import annotations

import asyncio
import re
import threading
from datetime import datetime, timedelta, timezone
from queue import Queue
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from Server.api import Job, clean, format_skills, is_tech_role, keeps_india_hybrid_or_remote, within_days
from Server.feeds import SidecarConnector

BASE_URL = "https://www.naukri.com"
# Date order stops a search once a page is entirely outside the 15-day window.
MAX_PAGES = 40
DETAIL_TABS = 4
CARD = "div.srp-jobtuple-wrapper"
TECH_QUERIES = (
    "software engineer",
    "software developer",
    "frontend developer",
    "backend developer",
    "full stack developer",
    "java developer",
    "python developer",
    "react developer",
    "nodejs developer",
    "dotnet developer",
    "golang developer",
    "php developer",
    "android developer",
    "ios developer",
    "data engineer",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "devops engineer",
    "cloud engineer",
    "sre",
    "qa automation",
    "sdet",
    "cybersecurity",
    "network engineer",
    "database administrator",
    "ui developer",
    "embedded software",
    "salesforce developer",
    "technical support",
)
_BLOCKED = ("access denied", "verify you are human", "captcha", "unusual traffic", "robot check")
_RELATIVE = re.compile(r"(\d+)\+?\s*(day|week|month)s?", re.I)


def search_url(keyword: str, page_number: int, *, remote: bool = False) -> str:
    """Public Naukri search. Page 1 has no suffix; later pages are `-2`, `-3`, ..."""
    slug = quote_plus(clean(keyword)).replace("+", "-")
    prefix = "work-from-home-" if remote else ""
    url = f"{BASE_URL}/{prefix}{slug}-jobs"
    if page_number > 1:
        url += f"-{page_number}"
    return f"{url}?sort=f"


def posted_from_label(label: str) -> str:
    """Turn '1 day ago' into the UTC timestamp the other portals use."""
    text = clean(label).casefold()
    if not text:
        return ""
    now = datetime.now(timezone.utc)
    if any(word in text for word in ("just now", "today", "hour", "minute")):
        moment = now
    else:
        match = _RELATIVE.search(text)
        if not match:
            return ""
        count = int(match.group(1))
        unit = match.group(2).casefold()
        days = count if unit == "day" else count * 7 if unit == "week" else count * 30
        moment = now - timedelta(days=days)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _text(node, selector: str) -> str:
    element = node.select_one(selector)
    if element is None:
        return ""
    return clean(element.get("title")) or clean(element.get_text(" ", strip=True))


def _first(node, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        text = _text(node, selector)
        if text:
            return text
    return ""


def _href(node, selector: str) -> str:
    element = node.select_one(selector)
    href = clean(element.get("href")) if element else ""
    if href.startswith("/"):
        href = BASE_URL + href
    return href.split("?")[0]


def cards_from_html(html: str) -> list[dict]:
    """Read the rendered search cards. Promoted widgets sit outside this list."""
    soup = BeautifulSoup(html or "", "html.parser")
    cards = []
    for node in soup.select(CARD):
        title_link = node.select_one("a.title")
        title = clean(title_link.get_text(" ", strip=True) if title_link else "") or _text(node, "h2")
        url = _href(node, "a.title") or _href(node, "a[href*='job-listings']")
        if not title and not url:
            continue
        salary = _first(node, (".sal span", ".sal", ".sal-wrap span"))
        if "not disclosed" in salary.casefold():
            salary = ""
        skill_nodes = node.select("li.tag-li") or node.select(".tags-gt li")
        skills = [clean(item.get_text(" ", strip=True)) for item in skill_nodes]
        cards.append({
            "title": title,
            "company": _first(node, ("a.comp-name", "a.subTitle")),
            "location": _first(node, (".locWdth", ".loc-wrap", ".job-location")),
            "experience": _first(node, (".expwdth", ".exp-wrap")),
            "salary": salary,
            "skills": [skill for skill in skills if skill],
            "description": _first(node, (".job-desc",)),
            "posted_at": posted_from_label(_first(node, (".job-post-day", ".job-post-date"))),
            "url": url,
        })
    return cards


def _heading(soup: BeautifulSoup, title: str):
    for heading in soup.find_all(["h2", "h3"]):
        if clean(heading.get_text(" ", strip=True)).casefold() == title:
            return heading
    return None


def _stat(soup: BeautifulSoup, name: str) -> str:
    for label in soup.find_all("label"):
        text = clean(label.get_text(" ", strip=True)).casefold().rstrip(":").strip()
        if text != name:
            continue
        value = label.find_next_sibling("span") or label.find_next("span")
        return clean(value.get_text(" ", strip=True)) if value else ""
    return ""


_STOP_HEADINGS = {"key skills", "about company", "similar jobs", "beware of imposters!"}


def _label_line(node) -> str:
    label = node.find("label")
    if label is None:
        return ""
    title = clean(label.get_text(" ", strip=True)).rstrip(":")
    value = clean(node.get_text(" ", strip=True))
    prefix = clean(label.get_text(" ", strip=True))
    if value.casefold().startswith(prefix.casefold()):
        value = value[len(prefix):].strip(" :")
    if title and value:
        return f"{title}: {value}"
    return ""


def _section_lines(heading) -> list[str]:
    """Text after the Job description heading, including divs that are not paragraphs or lists."""
    lines = []
    for element in heading.find_all_next(["h2", "h3", "h4", "h5", "p", "li", "div"]):
        name = element.name
        title = clean(element.get_text(" ", strip=True))
        folded = title.casefold()
        if name in {"h2", "h3", "h4"} and folded in _STOP_HEADINGS:
            break
        if name in {"h2", "h3", "h4", "h5"}:
            if title and folded != "job description":
                lines.append(title)
            continue
        if name == "li":
            if title:
                lines.append(f"- {title}")
            continue
        if name == "div" and element.find(["div", "p", "li", "ul", "ol", "h2", "h3", "h4", "h5"]):
            continue
        if name == "div":
            labeled = _label_line(element)
            if labeled:
                lines.append(labeled)
                continue
        for line in element.get_text("\n", strip=True).splitlines():
            line = clean(line)
            if not line or line.casefold() == "job description":
                continue
            if "preferred keyskills" in line.casefold():
                continue
            lines.append(line)
    return list(dict.fromkeys(lines))


def detail_from_html(html: str) -> dict:
    """Full description, openings, and applicants from a rendered job page."""
    soup = BeautifulSoup(html or "", "html.parser")
    description = ""
    heading = _heading(soup, "job description")
    if heading is not None:
        description = "\n".join(_section_lines(heading))
    about = ""
    about_heading = _heading(soup, "about company")
    if about_heading is not None:
        section = about_heading.find_parent("section")
        if section is not None:
            address = ""
            for label in section.find_all("label"):
                if clean(label.get_text(" ", strip=True)).casefold().rstrip(":") == "address":
                    value = label.find_next_sibling("span")
                    address = clean(value.get_text(" ", strip=True)) if value else ""
            body = clean(section.get_text(" ", strip=True))
            if body.casefold().startswith("about company"):
                body = body[len("about company"):].strip()
            if body.casefold().startswith("not mentioned"):
                about = f"Address: {address}" if address else ""
            else:
                about = body
    skills = []
    skill_heading = _heading(soup, "key skills")
    if skill_heading is not None:
        section = skill_heading.find_parent("div") or skill_heading.parent
        for chip in section.select("a span"):
            skill = clean(chip.get_text(" ", strip=True))
            if skill and skill.casefold() not in {"key skills"}:
                skills.append(skill)
    return {
        "description": description,
        "about": about,
        "openings": _stat(soup, "openings"),
        "applicants": _stat(soup, "applicants"),
        "skills": list(dict.fromkeys(skills)),
    }


def _minimum_experience(experience: str, title: str) -> int | None:
    numbers = [int(value) for value in re.findall(r"\d{1,2}", experience or "")]
    if numbers:
        return min(numbers)
    folded = f"{experience} {title}".casefold()
    for words, years in (
        (("intern", "fresher", "graduate", "entry level", "trainee"), 0),
        (("junior",), 1),
        (("mid level", "intermediate"), 2),
        (("senior",), 3),
        (("lead", "staff", "principal", "architect", "manager"), 5),
    ):
        if any(word in folded for word in words):
            return years
    return None


def _keep(
    card: dict,
    posted_within_days: int | None,
    max_experience: int | None = None,
    roles: list[str] | None = None,
) -> bool:
    from Server.feeds import experience_cap, role_matches

    if not card.get("url") or not is_tech_role(card.get("title") or ""):
        return False
    if not keeps_india_hybrid_or_remote(card.get("location") or "India"):
        return False
    posted = card.get("posted_at") or ""
    if posted_within_days and posted and not within_days(posted, posted_within_days):
        return False
    skills = " ".join(card.get("skills") or [])
    if not role_matches(card.get("title") or "", skills, roles):
        return False
    minimum = _minimum_experience(card.get("experience") or "", card.get("title") or "")
    cap = experience_cap(max_experience)
    return cap is None or minimum is None or minimum <= cap


def _blocked(html: str) -> bool:
    text = clean(BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)).casefold()
    return any(phrase in text for phrase in _BLOCKED)


async def _launch(playwright):
    """Visible installed Chrome. Headless is rejected by Naukri before any cards exist."""
    try:
        return await playwright.chromium.launch(channel="chrome", headless=False)
    except Exception:
        return await playwright.chromium.launch(headless=False)


class Naukri(SidecarConnector):
    key = "naukri"
    label = "Naukri"

    def iter_items(self, query: str, posted_within_days: int | None):
        found: Queue = Queue()
        errors: list[BaseException] = []

        def run() -> None:
            try:
                asyncio.run(self._browse(found, query, posted_within_days))
            except Exception as exc:
                errors.append(exc)
            finally:
                found.put(None)

        threading.Thread(target=run, name="naukri-browser", daemon=True).start()
        while True:
            item = found.get()
            if item is None:
                break
            yield item
        if errors:
            raise errors[0]

    async def _browse(self, found: Queue, query: str, posted_within_days: int | None) -> None:
        selected = tuple(getattr(self, "search_phrases", None) or ())
        if not selected:
            selected = tuple(clean(item) for item in query.split(",") if clean(item))
        searches = selected or TECH_QUERIES
        async with async_playwright() as playwright:
            browser = await _launch(playwright)
            context = await browser.new_context(locale="en-IN", viewport={"width": 1440, "height": 900})
            page = await context.new_page()
            page.set_default_timeout(15000)
            try:
                for remote in (False, True):
                    for search in searches:
                        await self._pages(context, page, found, search, remote, posted_within_days)
            finally:
                await browser.close()

    async def _pages(self, context, page, found: Queue, search: str, remote: bool, posted_within_days: int | None) -> None:
        for page_number in range(1, MAX_PAGES + 1):
            url = search_url(search, page_number, remote=remote)
            try:
                html = await self._open(page, url)
            except RuntimeError as exc:
                if "denied" in str(exc).casefold():
                    raise
                self.warnings.append(str(exc))
                return
            cards = cards_from_html(html)
            if not cards:
                return
            await self._fill_details(context, [
                card for card in cards
                if _keep(
                    card,
                    posted_within_days,
                    getattr(self, "max_experience", None),
                    getattr(self, "role_terms", None),
                )
            ])
            for card in cards:
                found.put(card)
            dated = [card["posted_at"] for card in cards if card["posted_at"]]
            if posted_within_days and dated and all(
                not within_days(stamp, posted_within_days) for stamp in dated
            ):
                return

    async def _fill_details(self, context, cards: list[dict]) -> None:
        """Open kept jobs in parallel tabs, read the full posting, then close the tabs."""
        for start in range(0, len(cards), DETAIL_TABS):
            await asyncio.gather(*(self._read_detail(context, card) for card in cards[start:start + DETAIL_TABS]))

    async def _read_detail(self, context, card: dict) -> None:
        tab = await context.new_page()
        try:
            await tab.goto(card["url"], wait_until="domcontentloaded", timeout=45000)
            try:
                await tab.wait_for_function(
                    """() => {
                      const heading = [...document.querySelectorAll('h2, h3')]
                        .find((node) => /job description/i.test(node.textContent || ''))
                      const section = heading && (heading.closest('section') || heading.parentElement)
                      return Boolean(section && (section.innerText || '').length > 250)
                    }""",
                    timeout=15000,
                )
            except PlaywrightTimeoutError:
                pass
            detail = detail_from_html(await tab.content())
        except Exception as exc:
            self.warnings.append(f"detail skipped: {exc}")
            return
        finally:
            await tab.close()
        if detail.get("description"):
            card["description"] = detail["description"]
        if detail.get("about"):
            card["about"] = detail["about"]
        card["openings"] = detail.get("openings") or ""
        card["applicants"] = detail.get("applicants") or ""
        if detail.get("skills"):
            card["skills"] = detail["skills"]

    async def _open(self, page, url: str) -> str:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Naukri search timed out: {url}") from exc
        html = await page.content()
        if _blocked(html):
            raise RuntimeError("Naukri denied the browser before the job list loaded")
        for selector in ("button[aria-label='Close']", ".crossIcon"):
            try:
                await page.locator(selector).first.click(timeout=800)
                break
            except Exception:
                pass
        try:
            await page.locator("#filter-sort").click(timeout=2500)
            await page.locator("a[data-id='filter-sort-f']").click(timeout=2500)
            await page.wait_for_selector(CARD, timeout=15000)
        except Exception:
            try:
                await page.wait_for_selector(CARD, timeout=12000)
            except PlaywrightTimeoutError:
                return await page.content()
        for _ in range(3):
            await page.mouse.wheel(0, 2200)
            await page.wait_for_timeout(350)
        return await page.content()

    def parse_item(self, item: dict) -> Job:
        return Job(
            source=self.label,
            title=item.get("title") or "",
            company=item.get("company") or "",
            location=item.get("location") or "India",
            url=item.get("url") or "",
            posted_at=item.get("posted_at") or "",
            experience=item.get("experience") or "",
            skill=format_skills(item.get("skills") or []),
            salary=item.get("salary") or "",
            about_company=item.get("about") or "",
            job_description=item.get("description") or "",
            openings=item.get("openings") or "",
            applicants=item.get("applicants") or "",
        )
