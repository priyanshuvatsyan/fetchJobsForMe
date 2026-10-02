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

    def test_role_abbreviations_expand_before_search(self):
        import requests
        from unittest.mock import patch

        from Server.feeds import role_matches, search_phrases
        from connectors.Jobicy.Jobicy import jobicy_tags

        self.assertEqual(
            search_phrases(["ML"]),
            ["ML", "machine learning", "ml engineer", "mlops"],
        )
        self.assertTrue(role_matches("Machine Learning Engineer", "", ["ML"]))
        self.assertTrue(role_matches("MLOps Engineer", "Python", ["ML"]))
        self.assertFalse(role_matches("Email Marketing Specialist", "", ["AI"]))
        self.assertTrue(role_matches("AI Engineer", "", ["AI"]))
        self.assertEqual(
            jobicy_tags(["devops", "developer", "ML"]),
            ["devops", "software-development", "machine-learning"],
        )
        self.assertNotIn("ML", jobicy_tags(["ML"]))

        class Response:
            def __init__(self, status, payload):
                self.status_code = status
                self._payload = payload

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError("bad tag")

            def json(self):
                return self._payload

        calls = []

        def fake_get(url, params, headers, timeout):
            del url, headers, timeout
            tag = params.get("tag")
            calls.append(tag)
            if tag == "devops":
                return Response(400, {})
            return Response(200, {"jobs": [{"id": tag}]})

        connector = Jobicy()
        connector.role_terms = ["devops", "ML"]
        with patch("connectors.Jobicy.Jobicy.requests.get", fake_get):
            items = list(connector.iter_items("", None))
        self.assertEqual(calls, ["devops", "machine-learning"])
        self.assertEqual(items, [{"id": "machine-learning"}])
        self.assertTrue(connector.warnings)

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
        import Server.server as server

        original = server._saved_memory
        server._saved_memory = {}
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
            stored = server.save_job("user-one", job)
            self.assertEqual(stored["portalKey"], "fourdayweek")
            self.assertTrue(stored["saved at"])
            self.assertNotIn("unexpected", stored)
            self.assertEqual(server.save_job("user-one", job)["saved at"], stored["saved at"])
            self.assertEqual(len(server.read_saved("user-one")), 1)
            self.assertEqual(server.read_saved("user-two"), [])
            with self.assertRaises(ValueError):
                server.save_job("user-one", {"role": "No link"})
            self.assertTrue(server.unsave_job("user-one", job["link"]))
            self.assertFalse(server.unsave_job("user-one", job["link"]))
            self.assertEqual(server.read_saved("user-one"), [])
        finally:
            server._saved_memory = original

    def test_resume_import_and_manual_profile_update(self):
        import base64
        import tempfile
        from pathlib import Path

        import Server.server as server

        store = {"data": None}

        class _Document:
            def get(self):
                class _Snapshot:
                    exists = store["data"] is not None
                    def to_dict(_self):
                        return dict(store["data"] or {})
                return _Snapshot()

            def set(self, data, merge=False):
                current = dict(store["data"] or {})
                store["data"] = {**current, **data} if merge else dict(data)

        original_document = server._profile_document
        server._profile_document = lambda uid: _Document()
        resume = """Shubhak Example
Senior Backend Engineer
shubhak@example.com | +91 9876543210
https://linkedin.com/in/shubhak https://github.com/shubhak

SUMMARY
Backend engineer with 5 years of experience building Python and FastAPI services on AWS.

EXPERIENCE
Senior Backend Engineer, Acme
Built REST APIs with PostgreSQL, Docker, Kubernetes and Kafka.

EDUCATION
B.Tech Computer Science, Example University
"""
        try:
            result = server.upload_resume("user-one", {
                "filename": "resume.txt",
                "content": base64.b64encode(resume.encode()).decode(),
            })
            profile = result["profile"]
            self.assertEqual(profile["email"], "shubhak@example.com")
            self.assertEqual(profile["totalExperience"], "5 years")
            self.assertIn("Python", profile["skills"])
            self.assertIn("FastAPI", profile["skills"])
            self.assertEqual(profile["resume"]["filename"], "resume.txt")
            updated = server.update_profile("user-one", {
                "targetRoles": ["Backend Engineer"],
                "preferredLocations": ["Bengaluru", "Remote"],
                "openToWork": True,
            })
            self.assertTrue(updated["openToWork"])
            self.assertEqual(updated["targetRoles"], ["Backend Engineer"])
            self.assertGreater(updated["completion"], profile["completion"])
        finally:
            server._profile_document = original_document


    def test_unstop_keeps_structure_and_fresher_eligibility(self):
        from Server.api import split_description
        from connectors.Unstop.Unstop import additional_information, experience_text

        html = (
            "<p><strong>About the Company</strong></p>\n<p>TipTap is a D2C brand.</p>\n"
            "<p><strong>What We&rsquo;re Looking For:</strong></p>\n<p>A creator.</p>\n"
            "<p><strong>What You&rsquo;ll Do:</strong></p>\n<ul><li>Shoot reels.</li><li>Edit videos.</li></ul>"
        )
        about, role = split_description(html)
        self.assertIn("TipTap is a D2C brand.", about)
        self.assertIn("\n- Shoot reels.\n- Edit videos.", role)
        item = {
            "filters": [
                {"type": "eligible", "name": "Fresher"},
                {"type": "eligible", "name": "Experienced Professionals"},
            ],
            "jobDetail": {"type": "in_office", "timing": "full_time"},
        }
        experience = experience_text({"min_experience": None}, "Content Creator", "", item)
        self.assertEqual(experience, "Fresher")
        extra = additional_information(item, experience)
        self.assertIn("Job Type: In Office", extra)
        self.assertIn("Eligibility: Fresher, Experienced Professionals", extra)

    def test_posting_facts_keep_only_published_contact_and_counts(self):
        from Server.api import Job, posting_facts
        from Server.feeds import job_record

        facts = posting_facts(
            {
                "totalJobOpenings": 3,
                "applicationContact": {"name": "Ada Lovelace", "email": "ada@analytical.dev"},
                "hiringOrganization": {"name": "Acme"},
            },
            "Applicants: 40+",
        )
        self.assertEqual(facts["posted_by"], "Ada Lovelace")
        self.assertEqual(facts["email"], "ada@analytical.dev")
        self.assertEqual(facts["openings"], "3")
        self.assertEqual(facts["applicants"], "40+")
        self.assertEqual(posting_facts({}, "Build APIs with Python.")["email"], "")
        self.assertEqual(posting_facts({"hiringOrganization": {"name": "Acme"}}, "")["posted_by"], "")
        record = job_record(Job(
            source="Remotive",
            title="Software Engineer",
            company="Acme",
            location="Remote",
            url="https://example.com/job",
            job_description="Posted by: Grace Hopper\nEmail: grace@hopper.dev\n2 openings",
        ), "remotive")
        self.assertEqual(record["description"]["posted by"], "Grace Hopper")
        self.assertEqual(record["description"]["email"], "grace@hopper.dev")
        self.assertEqual(record["description"]["openings"], "2")
        self.assertNotIn("applicants", record["description"])

    def test_apply_link_falls_back_to_job_url(self):
        from Server.api import Job, apply_url_from_html
        from Server.feeds import job_record

        html = """
        <a href="https://in.indeed.com/viewjob?jk=abc">Software Engineer</a>
        <a href="https://jobs.acme.example/apply/42">Apply on company site</a>
        <a href="https://accounts.google.com/signin">Apply with Google</a>
        """
        self.assertEqual(
            apply_url_from_html(html, "https://in.indeed.com/viewjob?jk=abc"),
            "https://jobs.acme.example/apply/42",
        )
        same = job_record(Job(
            source="Indeed",
            title="Software Engineer",
            company="Acme",
            location="Bengaluru",
            url="https://in.indeed.com/viewjob?jk=abc",
        ), "indeed")
        self.assertEqual(same["apply"], same["link"])
        separate = job_record(Job(
            source="Indeed",
            title="Software Engineer",
            company="Acme",
            location="Bengaluru",
            url="https://in.indeed.com/viewjob?jk=abc",
            apply_url="https://jobs.acme.example/apply/42",
        ), "indeed")
        self.assertEqual(separate["link"], "https://in.indeed.com/viewjob?jk=abc")
        self.assertEqual(separate["apply"], "https://jobs.acme.example/apply/42")

    def test_indeed_card_parser(self):
        from Server.api import is_tech_role, keeps_india_hybrid_or_remote
        from connectors.Indeed.Indeed import cards_from_html, detail_from_html, search_url

        cards = cards_from_html("""
        <div class="job_seen_beacon">
          <h2 class="jobTitle"><a class="jcs-JobTitle" data-jk="abc123">Software Engineer</a></h2>
          <span data-testid="company-name">Acme Labs</span>
          <div data-testid="text-location">Hybrid work in Bengaluru, Karnataka</div>
          <div data-testid="attribute_snippet_testid salary-snippet-container">₹10,00,000 a year</div>
        </div>
        <div class="job_seen_beacon">
          <a class="jcs-JobTitle" data-jk="abc123">Software Engineer</a>
        </div>
        """)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["title"], "Software Engineer")
        self.assertEqual(card["company"], "Acme Labs")
        self.assertEqual(card["location"], "Hybrid work in Bengaluru, Karnataka")
        self.assertEqual(card["salary"], "₹10,00,000 a year")
        self.assertEqual(card["url"], "https://in.indeed.com/viewjob?jk=abc123")
        traps = cards_from_html("""
        <div class="job_seen_beacon" style="display:none">
          <a class="jcs-JobTitle" data-jk="fedcba9876543210">Software Engineer</a>
        </div>
        <div class="job_seen_beacon">
          <a class="jcs-JobTitle" data-jk="789abcdef0123456" href="/viewjob?jk=789abcdef0123456">Software Engineer</a>
        </div>
        <div class="job_seen_beacon">
          <a class="jcs-JobTitle" data-jk="ignored" href="/rc/clk?jk=a1b2c3d4e5f60789">Software Engineer</a>
        </div>
        """)
        self.assertEqual(
            [card["url"] for card in traps],
            ["https://in.indeed.com/viewjob?jk=a1b2c3d4e5f60789"],
        )
        from unittest import mock
        from connectors.Indeed.Indeed import BLOCKED_NOTE, Indeed

        connector = Indeed()
        connector.warnings = []
        connector._detail_blocked = False
        challenge = mock.Mock(status_code=403, text='<div id="cf-box-container"></div>')
        with mock.patch("connectors.Indeed.Indeed.requests.get", return_value=challenge) as get:
            self.assertEqual(connector._read_detail("https://in.indeed.com/viewjob?jk=1"), {})
            self.assertEqual(connector._read_detail("https://in.indeed.com/viewjob?jk=2"), {})
        self.assertTrue(connector._detail_blocked)
        self.assertEqual(connector.warnings, [BLOCKED_NOTE])
        self.assertEqual(get.call_count, 2)
        self.assertTrue(is_tech_role(card["title"]))
        self.assertTrue(keeps_india_hybrid_or_remote(card["location"]))
        self.assertIn("l=India", search_url("software engineer", 0, remote=False, fromage=15))
        self.assertIn("l=Remote", search_url("software engineer", 10, remote=True, fromage=1))
        detail = detail_from_html("""
        <script type="application/ld+json">
        {
          "@type": "JobPosting",
          "title": "Software Engineer",
          "datePosted": "2026-10-01T04:00:00Z",
          "description": "<p>About Acme Labs.</p><p>Build services with Python. 2 years of experience.</p>",
          "skills": ["Python", "SQL"],
          "hiringOrganization": {"name": "Acme Labs"},
          "jobLocation": {"address": {"addressLocality": "Bengaluru", "addressRegion": "Karnataka"}},
          "baseSalary": {"currency": "INR", "value": {"minValue": 200000, "maxValue": 800000, "unitText": "YEAR"}}
        }
        </script>
        """)
        self.assertIn("Build services with Python", detail["description"])
        self.assertEqual(detail["skill"], "Python, SQL")
        self.assertEqual(detail["posted_at"], "2026-10-01 04:00:00")
        self.assertIn("2 years", detail["experience"])
        self.assertEqual(detail["salary"], "₹200,000 - ₹800,000 a year")
        self.assertEqual(detail["location"], "Bengaluru, Karnataka")

    def test_naukri_card_parser(self):
        from Server.api import is_tech_role, keeps_india_hybrid_or_remote, within_days
        from connectors.Naukri.Naukri import cards_from_html, posted_from_label, search_url

        html = """
        <div class="srp-jobtuple-wrapper" data-job-id="011026012196">
          <h2><a class="title" href="https://www.naukri.com/job-listings-software-engineer-example-bengaluru-0-to-5-years-011026012196">Software Engineer</a></h2>
          <a class="comp-name" title="Example Labs">Example Labs</a>
          <span class="expwdth">0-5 Yrs</span>
          <span class="locWdth">Remote</span>
          <span class="sal"><span title="5-14 Lacs PA">5-14 Lacs PA</span></span>
          <span class="job-desc">Build services with Python.</span>
          <ul class="tags-gt"><li class="tag-li">Python</li><li class="tag-li">SQL</li></ul>
          <span class="job-post-day">1 day ago</span>
        </div>
        <div class="srp-job-promotion"><span class="title">Promoted role</span></div>
        """
        cards = cards_from_html(html)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["title"], "Software Engineer")
        self.assertEqual(card["company"], "Example Labs")
        self.assertEqual(card["location"], "Remote")
        self.assertEqual(card["experience"], "0-5 Yrs")
        self.assertEqual(card["salary"], "5-14 Lacs PA")
        self.assertEqual(card["skills"], ["Python", "SQL"])
        self.assertTrue(card["url"].endswith("011026012196"))
        self.assertTrue(is_tech_role(card["title"]))
        self.assertTrue(keeps_india_hybrid_or_remote(card["location"]))
        self.assertTrue(within_days(card["posted_at"], 15))
        old = posted_from_label("30+ days ago")
        self.assertFalse(within_days(old, 15))
        self.assertEqual(search_url("software engineer", 1), "https://www.naukri.com/software-engineer-jobs?sort=f")
        self.assertEqual(search_url("software engineer", 2), "https://www.naukri.com/software-engineer-jobs-2?sort=f")
        self.assertEqual(
            search_url("python developer", 1, remote=True),
            "https://www.naukri.com/work-from-home-python-developer-jobs?sort=f",
        )
        from connectors.Naukri.Naukri import detail_from_html

        detail = detail_from_html("""
        <section id="job_header">
          <span><label>Openings: </label><span>1</span></span>
          <span><label>Applicants: </label><span>100+</span></span>
        </section>
        <section>
          <div><h2>Job description</h2></div>
          <div>
            <div><p>Design CI/CD pipelines for Salesforce.</p><ul><li>Manage Git workflows.</li></ul></div>
            <div><label>Role: </label><span>Technical Consultant</span></div>
          </div>
        </section>
        <section>
          <h2>About company</h2>
          <div>Not mentioned</div>
          <div><label>Address:</label><span>Bagmane Tech Park, Bengaluru</span></div>
        </section>
        <div><h2>Key Skills</h2><div><a><span>Copado</span></a><a><span>Git</span></a></div></div>
        """)
        self.assertIn("Design CI/CD pipelines", detail["description"])
        self.assertIn("- Manage Git workflows.", detail["description"])
        self.assertIn("Role: Technical Consultant", detail["description"])
        self.assertEqual(detail["openings"], "1")
        self.assertEqual(detail["applicants"], "100+")
        self.assertEqual(detail["skills"], ["Copado", "Git"])
        self.assertIn("Bagmane Tech Park", detail["about"])
        plain = detail_from_html("""
        <section>
          <div><h2>Job description</h2></div>
          <div>
            <h3>Job Description</h3>
            <div>Works in the area of Software Engineering, which encompasses the development, maintenance and optimization of software solutions/applications.</div>
            <div>1. Applies scientific methods to analyse and solve software engineering problems.</div>
            <h3>Job Description - Grade Specific</h3>
            <div>Has more than a year of relevant work experience.</div>
            <div><label>Role: </label><span>Software Development - Other</span></div>
            <div>Education</div>
            <div><label>UG: </label><span>Any Graduate</span></div>
          </div>
          <h2><span>Key Skills</span></h2>
          <div>Skills highlighted with preferred keyskills</div>
          <div>Maintenance</div>
          <h3>Report this job</h3>
          <div>Inappropriate Content</div>
          <div>Beware of imposters!</div>
          <div>Naukri.com does not promise a job or an interview in exchange of money.</div>
          <div>Connect with us</div>
          <div>Apply on the go</div>
        </section>
        """)
        self.assertIn("Works in the area of Software Engineering", plain["description"])
        self.assertIn("1. Applies scientific methods", plain["description"])
        self.assertIn("Job Description - Grade Specific", plain["description"])
        self.assertIn("Has more than a year of relevant work experience.", plain["description"])
        self.assertIn("Role: Software Development - Other", plain["description"])
        self.assertIn("UG: Any Graduate", plain["description"])
        self.assertNotIn("Maintenance", plain["description"])
        self.assertNotIn("Report this job", plain["description"])
        self.assertNotIn("Beware of imposters", plain["description"])
        self.assertNotIn("Connect with us", plain["description"])
        self.assertNotIn("Apply on the go", plain["description"])
        bold = detail_from_html("""
        <section class="styles_job-desc-container__txpYf">
          <div><h2>Job description</h2></div>
          <div>
            <div>
              <p>We are seeking an experienced <strong>MRO Engineers</strong> with strong expertise in <strong>aerospace maintenance</strong>.</p>
              <br>
              <p><strong>Key Responsibilities</strong></p>
              <ul>
                <li>Investigate <strong>service damages</strong> on <strong>aero engine components</strong> and determine <strong>root causes</strong>.</li>
              </ul>
            </div>
            <div class="styles_other-details__oEN4O">
              <div><label>Role: </label><span><a>Other</a></span></div>
              <div><label>Industry Type: </label><span>IT Services &amp; Consulting</span></div>
            </div>
            <div>
              <div>Education</div>
              <div><label>UG: </label><span>B.Tech / B.E. in Mechanical Engineering</span></div>
            </div>
          </div>
          <div><div>Key Skills</div><div>Skills highlighted with preferred keyskills</div></div>
        </section>
        """)
        self.assertIn(
            "We are seeking an experienced MRO Engineers with strong expertise in aerospace maintenance.",
            bold["description"],
        )
        self.assertIn("Key Responsibilities", bold["description"])
        self.assertIn(
            "- Investigate service damages on aero engine components and determine root causes.",
            bold["description"],
        )
        self.assertNotIn("- service damages", bold["description"])
        self.assertIn("Role: Other", bold["description"])
        self.assertIn("Industry Type: IT Services & Consulting", bold["description"])
        self.assertIn("UG: B.Tech / B.E. in Mechanical Engineering", bold["description"])

    def test_user_search_preferences_filter_jobs(self):
        import tempfile
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        import Server.server as server

        original = server.PREFERENCES_DIR
        server.PREFERENCES_DIR = Path(tempfile.mkdtemp()) / "preferences"
        try:
            preferences = server.update_preferences("user-one", {
                "experience": 3,
                "posted": "today",
                "roles": ["DevOps", "ML"],
            })
            self.assertEqual(server.read_preferences("user-one"), preferences)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            old = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            jobs = [
                {"role": "DevOps Engineer", "experience": "3-7 Yrs", "skill": "", "added on": now},
                {"role": "Machine Learning Engineer", "experience": "0-5 Yrs", "skill": "", "added on": now},
                {"role": "DevOps Engineer", "experience": "", "skill": "", "added on": now},
                {"role": "DevOps Engineer", "experience": "4-6 Yrs", "skill": "", "added on": now},
                {"role": "DevOps Engineer", "experience": "0-2 Yrs", "skill": "", "added on": old},
                {"role": "Backend Engineer", "experience": "0-2 Yrs", "skill": "Python", "added on": now},
            ]
            filtered = server.apply_preferences({"jobs": jobs}, preferences)["jobs"]
            self.assertEqual(len(filtered), 3)
            self.assertTrue(any(job["experience"] == "" for job in filtered))

            broad = server.update_preferences("user-two", {
                "experience": None,
                "posted": "all",
                "roles": [],
            })
            self.assertIsNone(broad["experience"])
            self.assertEqual(broad["posted"], "all")
            self.assertEqual(server.preference_days(broad), 15)
            recent = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
            stale = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
            everything = server.apply_preferences({"jobs": [
                {"role": "Backend Engineer", "experience": "4-6 Yrs", "skill": "Python", "added on": recent},
                {"role": "Backend Engineer", "experience": "4-6 Yrs", "skill": "Python", "added on": stale},
                {"role": "Data Analyst", "experience": "", "skill": "", "added on": recent},
            ]}, broad)["jobs"]
            self.assertEqual(len(everything), 2)
            self.assertTrue(all(job["added on"] == recent for job in everything))
        finally:
            server.PREFERENCES_DIR = original


if __name__ == "__main__":
    unittest.main()
