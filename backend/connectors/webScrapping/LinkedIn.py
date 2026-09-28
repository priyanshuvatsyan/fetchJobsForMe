"""
Keywords and city go on LinkedIn's public search URL. The browser session is
the user's, so they stay signed in as themselves. This does not download listings.
"""

from __future__ import annotations

import urllib.parse
import webbrowser

SEARCH_URL = "https://www.linkedin.com/jobs/search/"


def linkedin_job_search_url(keywords: str, city: str) -> str:
    """Build https://www.linkedin.com/jobs/search/?keywords=...&location=..."""
    params = {
        "keywords": (keywords or "").strip(),
        "location": (city or "").strip(),
        "position": "1",
        "pageNum": "0",
    }
    return f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"


def open_linkedin_job_search(keywords: str, city: str) -> str:
    """Open the search URL so LinkedIn uses the account already in the browser."""
    url = linkedin_job_search_url(keywords, city)
    webbrowser.open(url, new=2)
    return url


class LinkedIn:
    key = "linkedin"
    label = "LinkedIn"

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.search_url = ""
        self.opened = False

    def fetch(
        self,
        query: str = "",
        where: str = "",
        limit: int = 10,
        boards: list[str] | None = None,
        open_browser: bool = True,
    ) -> list:
        del limit, boards
        keywords = query.strip()
        city = where.strip()
        self.search_url = linkedin_job_search_url(keywords, city)
        if open_browser:
            open_linkedin_job_search(keywords, city)
            self.opened = True
            self.warnings = [
                "Opened in your browser. You stay on LinkedIn as yourself."
            ]
        else:
            self.opened = False
            self.warnings = [
                "Search URL is ready. Open it while you are signed in on LinkedIn."
            ]
        return []
