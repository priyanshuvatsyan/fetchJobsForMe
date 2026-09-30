"""We Work Remotely's public programming-jobs RSS feed."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from Server.api import Job, clean, job_profile, plain_text, split_description, to_datetime
from Server.feeds import SidecarConnector

RSS_URL = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
HEADERS = {"User-Agent": "fetchJobsForMe/0.1", "Accept": "application/rss+xml, application/xml"}


def _child_text(node, name: str) -> str:
    child = node.find(name)
    return child.text if child is not None and child.text else ""


class WeWorkRemotely(SidecarConnector):
    key = "weworkremotely"
    label = "We Work Remotely"

    def iter_items(self, query: str, posted_within_days: int | None):
        response = requests.get(RSS_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        for node in root.findall("./channel/item"):
            item = {name: _child_text(node, name) for name in (
                "title", "region", "category", "description", "pubDate", "guid", "link"
            )}
            if not query or query.casefold() in (
                f"{item['title']} {item['category']} {plain_text(item['description'])}".casefold()
            ):
                yield item

    def parse_item(self, item: dict) -> Job:
        combined = clean(item.get("title"))
        company, separator, title = combined.partition(":")
        if not separator:
            company, title = "", combined
        body = item.get("description") or ""
        about, description = split_description(body)
        posted = ""
        if item.get("pubDate"):
            try:
                posted = to_datetime(parsedate_to_datetime(item["pubDate"]).isoformat())
            except (TypeError, ValueError):
                posted = ""
        experience, skill = job_profile(title, body, [item.get("category")])
        return Job(
            source=self.label,
            title=clean(title),
            company=clean(company),
            location=f"{clean(item.get('region')) or 'Anywhere'} (Remote)",
            url=clean(item.get("link") or item.get("guid")),
            posted_at=posted,
            experience=experience,
            skill=skill,
            about_company=about,
            job_description=description or plain_text(body),
        )
