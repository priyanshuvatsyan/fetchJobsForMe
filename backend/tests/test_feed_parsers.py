"""Parser checks for the independent public job feeds."""

from __future__ import annotations

import unittest

from Server.api import is_tech_role, keeps_india_hybrid_or_remote, to_datetime
from connectors.FourDayWeek import FourDayWeek
from connectors.Himalayas import Himalayas
from connectors.Instahyre import Instahyre
from connectors.Jobicy import Jobicy
from connectors.Shine import Shine
from connectors.TheMuse import TheMuse
from connectors.WeWorkRemotely import WeWorkRemotely
from connectors.WorkingNomads import WorkingNomads


class FeedParserTests(unittest.TestCase):
    def test_himalayas(self):
        job = Himalayas().parse_item({
            "title": "Backend Engineer",
            "companyName": "Acme",
            "locationRestrictions": ["India"],
            "applicationLink": "https://himalayas.app/jobs/1",
            "pubDate": 1_797_552_000,
            "seniority": ["Senior"],
            "categories": ["Python"],
            "description": "<p>Build APIs</p>",
        })
        self.assertEqual(job.location, "India (Remote)")
        self.assertEqual(job.skill, "Python")

    def test_jobicy(self):
        job = Jobicy().parse_item({
            "jobTitle": "Data Engineer",
            "companyName": "Acme",
            "jobGeo": "APAC",
            "url": "https://jobicy.com/jobs/1",
            "pubDate": "2026-09-30T04:00:00Z",
            "jobLevel": "Senior",
            "jobIndustry": ["Data Science"],
            "jobDescription": "<p>SQL pipelines</p>",
            "salaryMin": 100000,
            "salaryMax": 120000,
            "salaryCurrency": "USD",
            "salaryPeriod": "yearly",
        })
        self.assertEqual(job.salary, "USD 100,000–120,000/yearly")
        self.assertIn("Remote", job.location)

    def test_four_day_week_salary_is_cents(self):
        job = FourDayWeek().parse_item({
            "title": "Software Engineer",
            "company": {"name": "Acme"},
            "locations": [{"country": "India"}],
            "url": "https://4dayweek.io/job/1",
            "posted_at": "2026-09-30T04:00:00Z",
            "skills": [{"name": "Python"}],
            "salary_min": 10_000_000,
            "salary_max": 12_000_000,
            "salary_currency": "USD",
            "salary_period": "year",
            "description": "Build software",
        })
        self.assertEqual(job.salary, "USD 100,000–120,000/year")
        self.assertEqual(job.skill, "Python")

    def test_the_muse(self):
        job = TheMuse().parse_item({
            "name": "Cloud Engineer",
            "company": {"name": "Acme"},
            "locations": [{"name": "Remote"}],
            "refs": {"landing_page": "https://themuse.com/jobs/1"},
            "publication_date": "2026-09-30T04:00:00Z",
            "levels": [{"name": "Mid Level"}],
            "categories": [{"name": "Software Engineering"}],
            "contents": "<p>Cloud systems</p>",
        })
        self.assertEqual(job.experience, "Mid Level")
        self.assertEqual(job.skill, "Software Engineering")

    def test_working_nomads(self):
        job = WorkingNomads().parse_item({
            "title": "DevOps Engineer",
            "company_name": "Acme",
            "location": "Worldwide",
            "url": "https://workingnomads.com/job/1",
            "pub_date": "2026-09-30T04:00:00-04:00",
            "tags": "aws,kubernetes",
            "description": "<p>Operate clusters</p>",
        })
        self.assertEqual(job.skill, "aws, kubernetes")
        self.assertEqual(job.posted_at, "2026-09-30 08:00:00")

    def test_wwr_rss_item(self):
        job = WeWorkRemotely().parse_item({
            "title": "Acme: Senior Software Engineer",
            "region": "Anywhere",
            "category": "Full-Stack Programming",
            "description": "<p>Build software</p>",
            "pubDate": "Wed, 30 Sep 2026 04:00:00 +0000",
            "link": "https://weworkremotely.com/remote-jobs/1",
        })
        self.assertEqual(job.company, "Acme")
        self.assertEqual(job.title, "Senior Software Engineer")

    def test_shine_india_timestamp(self):
        job = Shine().parse_item({
            "jJT": "Python Developer",
            "jCName": "Acme",
            "jLoc": ["Pune"],
            "jSlug": "python-developer/acme/1",
            "jPDate": "2026-09-30T12:30:00",
            "jKwd": "python,django",
            "jExp": "2 to 4 Yrs",
            "jJD": "Build APIs",
        })
        self.assertEqual(job.posted_at, "2026-09-30 07:00:00")
        self.assertEqual(job.skill, "python, django")

    def test_instahyre_date_is_unknown(self):
        job = Instahyre().parse_item({
            "title": "ML Engineer",
            "locations": "Bangalore",
            "public_url": "https://instahyre.com/job-1/",
            "keywords": ["Python", "PyTorch"],
            "employer": {"company_name": "Acme", "instahyre_note": "AI company"},
        })
        self.assertEqual(job.posted_at, "")
        self.assertEqual(job.skill, "Python, PyTorch")

    def test_timezone_and_cse_filter(self):
        self.assertEqual(
            to_datetime("2026-09-30 12:48:30 GMT+0530"),
            "2026-09-30 07:18:30",
        )
        self.assertTrue(is_tech_role("Solutions Architect"))
        self.assertFalse(is_tech_role("Non IT Recruiter"))
        self.assertFalse(is_tech_role("Production Engineer"))
        self.assertTrue(keeps_india_hybrid_or_remote("Bengaluru, India (Hybrid)"))
        self.assertTrue(keeps_india_hybrid_or_remote("Work From Home"))
        self.assertTrue(keeps_india_hybrid_or_remote("United States (Remote)"))
        self.assertTrue(keeps_india_hybrid_or_remote("Bangalore"))
        self.assertTrue(keeps_india_hybrid_or_remote("Bengaluru"))
        self.assertTrue(keeps_india_hybrid_or_remote("Mohali"))
        self.assertTrue(keeps_india_hybrid_or_remote("Pimpri Chinchwad"))
        self.assertTrue(keeps_india_hybrid_or_remote("Cochin (Hybrid)"))
        self.assertTrue(keeps_india_hybrid_or_remote("Thane"))
        self.assertFalse(keeps_india_hybrid_or_remote("Salem, Oregon, United States"))
        self.assertFalse(keeps_india_hybrid_or_remote("San Francisco, California, United States (Hybrid)"))
        self.assertFalse(keeps_india_hybrid_or_remote("Austin, TX"))

    def test_stop_keeps_jobs_already_saved(self):
        from Server.api import Job
        from Server.control import arm, cancel
        from Server.feeds import SidecarConnector, get_store

        class Demo(SidecarConnector):
            key = "stopdemo"
            label = "Stop Demo"

            def iter_items(self, query, posted_within_days):
                for index in range(6):
                    yield {
                        "title": f"Software Engineer {index}",
                        "url": f"https://example.com/jobs/{index}",
                    }
                    if index == 1:
                        cancel()

            def parse_item(self, item):
                return Job(
                    source=self.label,
                    title=item["title"],
                    company="Acme",
                    location="Remote",
                    url=item["url"],
                    skill="Python",
                )

        arm()
        try:
            jobs = Demo().fetch(limit=0, posted_within_days=30)
            self.assertEqual(
                [job.title for job in jobs],
                ["Software Engineer 0", "Software Engineer 1"],
            )
            self.assertEqual(len(get_store("stopdemo").read()), 2)
            self.assertTrue(all(record.get("portalKey") == "stopdemo" for record in get_store("stopdemo").read()))
        finally:
            arm()
            get_store("stopdemo").path.unlink(missing_ok=True)

    def test_flush_keeps_file_of_idle_store(self):
        import json

        from Server.feeds import get_store

        store = get_store("flushdemo")
        try:
            store.path.write_text(json.dumps([{"role": "Kept"}]), encoding="utf-8")
            store.flush()
            self.assertEqual(json.loads(store.path.read_text(encoding="utf-8")), [{"role": "Kept"}])
        finally:
            store.path.unlink(missing_ok=True)

    def test_portal_key_matches_every_label(self):
        from Server.server import CONNECTORS, with_note_key, with_portal_key

        labels = [cls.label.casefold() for cls in CONNECTORS]
        self.assertEqual(len(labels), len(set(labels)))
        for cls in CONNECTORS:
            record = with_portal_key({"portal": cls.label, "role": "Engineer"})
            self.assertEqual(record["portalKey"], cls.key)
            note = with_note_key({"portal": cls.label, "message": "slow"})
            self.assertEqual(note["portalKey"], cls.key)
        week = with_portal_key({"portal": "4 Day Week"})
        self.assertEqual(week["portalKey"], "fourdayweek")
        kept = with_portal_key({"portal": "4 Day Week", "portalKey": "fourdayweek"})
        self.assertIs(kept, with_portal_key(kept))

    def test_saved_jobs_round_trip(self):
        import tempfile
        from pathlib import Path

        import Server.server as server

        original = server.SAVED_FILE
        server.SAVED_FILE = Path(tempfile.mkdtemp()) / "saved_jobs.json"
        try:
            job = {
                "portal": "4 Day Week",
                "company": "JumpCloud",
                "role": "Escalations Engineer",
                "location": "Turkey (Remote)",
                "link": "https://4dayweek.io/job/1",
                "description": {"about company": "", "job description": "Fix things"},
                "unexpected": "dropped",
            }
            stored = server.save_job(job)
            self.assertEqual(stored["portalKey"], "fourdayweek")
            self.assertTrue(stored["saved at"])
            self.assertNotIn("unexpected", stored)
            self.assertEqual(server.save_job(job)["saved at"], stored["saved at"])
            self.assertEqual(len(server.read_saved()), 1)
            with self.assertRaises(ValueError):
                server.save_job({"role": "No link"})
            self.assertTrue(server.unsave_job(job["link"]))
            self.assertFalse(server.unsave_job(job["link"]))
            self.assertEqual(server.read_saved(), [])
        finally:
            server.SAVED_FILE.unlink(missing_ok=True)
            server.SAVED_FILE = original


if __name__ == "__main__":
    unittest.main()
