import { useState } from 'react'
import { Link } from 'react-router-dom'
import { auth } from '../../firebase'
import './Dashboard.css'

const jobs = [
	{
		id: 'devops',
		title: 'DevOps Engineer',
		company: 'Example Technologies',
		match: 87,
		location: 'Austin, TX · Hybrid',
		experience: '0–2 years',
		salary: '$105k–$132k',
		source: 'LinkedIn · Posted 2h ago',
		tags: ['Kubernetes', 'Docker', 'AWS', 'Linux', 'Terraform · missing'],
		insight: 'Your experience aligns with 8 of 9 core requirements.',
	},
	{
		id: 'cloud-platform',
		title: 'Cloud Platform Engineer',
		company: 'Northstar Systems',
		match: 84,
		location: 'Remote · US',
		experience: '2+ years',
		salary: '$118k–$148k',
		source: 'Greenhouse · Posted 5h ago',
		tags: ['Python', 'AWS', 'CI/CD', 'Docker', 'EKS · missing'],
		insight: 'Strong cloud and automation overlap. Add a recent Kubernetes project to strengthen your application.',
	},
]

const activity = [
	{ time: '09:42', text: 'Scraped 124 jobs', detail: '6 portals completed', tone: 'green' },
	{ time: '09:44', text: 'Filtered 81 relevant jobs', detail: 'Location, seniority, duplicates', tone: 'blue' },
	{ time: '09:47', text: 'Found 8 high-match jobs', detail: '3 above your 85% threshold', tone: 'purple' },
	{ time: '09:49', text: 'Completed 8 AI analyses', detail: 'Average against verified profile', tone: 'blue' },
	{ time: '09:52', text: 'Detected 1 interview email', detail: 'Example Technologies', tone: 'amber' },
]

export default function Dashboard() {
	const [search, setSearch] = useState('')
	const [selectedJob, setSelectedJob] = useState(jobs[0])
	const userName = auth.currentUser?.displayName || auth.currentUser?.email || 'Job seeker'
	const firstName = auth.currentUser?.displayName?.split(' ')[0] || 'there'
	const userInitials = userName.split('@')[0].split(/[ ._-]+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
	const query = search.trim().toLowerCase()
	const visibleJobs = query
		? jobs.filter((job) => [job.title, job.company, job.location, ...job.tags].join(' ').toLowerCase().includes(query))
		: jobs

	return (
		<div className="dashboard-page">
			<header className="dashboard-topbar">
				<label className="global-search">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
						<circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" />
					</svg>
					<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search jobs, companies, applications..." aria-label="Search jobs and companies" />
					<kbd>⌘ K</kbd>
				</label>
				<div className="topbar-tools">
					<span className="preview-indicator"><span />Preview data</span>
					<Link to="/email-responses" className="notification-button" aria-label="Open email and responses">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
							<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
						</svg>
					</Link>
					<div className="user-chip"><span>{userInitials || 'JS'}</span><div><strong>{userName}</strong><small>Job seeker</small></div></div>
				</div>
			</header>

			<main className="dashboard-content">
				<section className="dashboard-welcome">
					<div>
						<h1>Good morning, {firstName}</h1>
						<p>Your agent searched 6 portals and ranked 43 new roles while you were away.</p>
					</div>
					<Link className="run-search-button" to="/job-discovery">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M12 3v5m0 8v5m9-9h-5M8 12H3m15.4-6.4-3.5 3.5M9.1 14.9l-3.5 3.5m12.8 0-3.5-3.5M9.1 9.1 5.6 5.6" /></svg>
						Run search now
					</Link>
				</section>

				<section className="dashboard-metrics" aria-label="Job search statistics">
					{[
						['Jobs Found Today', '43', '+18 vs yesterday', 'blue'],
						['High Match Jobs', '8', '3 above 85%', 'purple'],
						['Applications Sent', '5', '2 awaiting review', 'green'],
						['Interviews', '3', '1 new invitation', 'green'],
						['Rejections', '7', '2 this week', 'red'],
						['Response Rate', '28%', '+6.2% this month', 'amber'],
					].map(([label, value, note, color]) => (
						<div className="metric-tile" key={label}>
							<div className="metric-label">{label}<span className={`metric-icon ${color}`} aria-hidden="true" /></div>
							<strong>{value}</strong>
							<small className={color}>{note}</small>
						</div>
					))}
				</section>

				<div className="dashboard-grid">
					<section className="recommendations-panel">
						<div className="dashboard-section-heading">
							<div><h2>AI Job Recommendations</h2><p>Ranked by verified skills, goals, and response likelihood</p></div>
							<Link to="/recommended-jobs">View all <span>→</span></Link>
						</div>
						<div className="recommendation-list">
							{visibleJobs.length ? visibleJobs.map((job) => (
								<article className={`job-card${selectedJob.id === job.id ? ' selected' : ''}`} key={job.id} onClick={() => setSelectedJob(job)}>
									<div className="job-card-main">
										<div className="job-copy">
											<div className="job-title-line"><h3>{job.title}</h3><span className="quality-badge">{job.match >= 85 ? 'High quality' : 'Strong match'}</span></div>
											<p className="job-company">{job.company}</p>
										</div>
										<div className="match-ring" style={{ '--match': `${job.match}%` }}><strong>{job.match}%</strong><small>MATCH</small></div>
									</div>
									<div className="job-details">
										<span>{job.location}</span><span>{job.experience}</span><span>{job.salary}</span>
									</div>
									<div className="job-tags">{job.tags.map((tag) => <span className={tag.includes('missing') ? 'missing' : ''} key={tag}>{tag}</span>)}</div>
									<footer className="job-card-footer">
										<span>{job.source}</span>
										<div><Link to="/resume-analyzer" onClick={(event) => event.stopPropagation()}>Analyze</Link><Link className="apply-button" to="/applications" onClick={(event) => event.stopPropagation()}>Apply <span>↗</span></Link></div>
									</footer>
								</article>
							)) : <p className="no-results">No preview jobs match “{search}”. Try another search.</p>}
						</div>
					</section>

					<aside className="match-insight">
						<div className="insight-heading"><span className="insight-sparkle">✦</span><div><small>AI INSIGHT</small><h2>Why this job matches you</h2></div></div>
						<p>{selectedJob.insight}</p>
						<ul>
							<li><span>✓</span>Build CI/CD workflows in Python</li>
							<li><span>✓</span>Deployed containerized services to AWS</li>
							<li><span>✓</span>2 years matches junior-level scope</li>
						</ul>
						<div className="insight-warning"><strong>△</strong><span>Terraform is preferred, not required. Be factual when it is not in your experience.</span></div>
						<Link className="review-application" to="/applications">Review application <span>→</span></Link>
					</aside>
				</div>

				<div className="dashboard-lower-grid">
					<section className="activity-panel">
						<div className="dashboard-section-heading"><div><h2>Agent activity</h2><p>Recent work from your job-search agent</p></div><span className="live-status"><span />Live</span></div>
						<div className="activity-table">
							{activity.map((item) => <div className="activity-row" key={item.time}><time>{item.time}</time><span className={`activity-dot ${item.tone}`} /><strong>{item.text}</strong><small>{item.detail}</small></div>)}
						</div>
					</section>
					<section className="approval-panel">
						<div className="dashboard-section-heading"><div><h2>Approval queue</h2><p>Items awaiting your review</p></div><span className="queue-count">2 waiting</span></div>
						<div className="queue-item"><span className="company-avatar">ET</span><div><strong>DevOps Engineer</strong><small>Example Technologies · 91% match</small></div><Link to="/applications">Review</Link></div>
						<div className="queue-item muted"><span className="loading-ring" /><div><strong>Analyzing Cloud Engineer</strong><small>Vector Labs · in progress</small></div></div>
					</section>
				</div>
				<p className="preview-note">Preview content shown for layout purposes. Live job and activity data is not connected yet.</p>
			</main>
		</div>
	)
}
