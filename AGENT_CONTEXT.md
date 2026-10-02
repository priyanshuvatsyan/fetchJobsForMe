# Agent handoff: fetchJobsForMe

## What this project does

`fetchJobsForMe` combines a Python job-fetching service/CLI with a React web app. The backend retrieves and normalizes openings from public job-board APIs and company boards; the web app lets users browse, filter, save, and inspect those openings. Firebase Auth is used for sign-in, and Firestore stores user preferences and the Gemini API key used by the AI endpoint.

## Repository map

- `backend/Server/`
  - `server.py`: CLI entry point and threaded JSON HTTP API. Registers connectors, runs refreshes, manages job/profile/resume/saved-job data, and serves `/api/*`.
  - `api.py`: shared HTTP/API client, job model, normalization, parsing, and filtering helpers.
  - `feeds.py`: common sidecar-feed persistence and matching logic for independently stored feeds.
  - `control.py`: shared cancellation/generation state for concurrent fetches.
  - `firebase.py`, `gemini_service.py`: Firebase Admin/Firestore and authenticated Gemini client helpers.
- `backend/connectors/`: one adapter/package per source (Greenhouse, Lever, Ashby, Remotive, RemoteOK, Arbeitnow, Adzuna, LinkedIn, Unstop, Shine, Indeed, Naukri, Instahyre, Himalayas, Jobicy, The Muse, Working Nomads, Four Day Week, and We Work Remotely). `companies.py` contains company-board slugs.
- `backend/tests/`: Python `unittest` coverage, including feed parsing and role matching.
- `backend/data/`: runtime JSON job/profile/saved/preference data and uploaded resume files. It is ignored by Git; treat its contents as user/runtime data.
- `backend/secrets/`: Firebase service-account location. Never read, copy, or commit credentials.
- `frontend/src/App.jsx`: React Router, Firebase session guard, shared layout, and route table.
- `frontend/src/api/`: browser API and data access helpers; `client.js` supplies the backend client, while preferences are currently read/written directly through Firestore.
- `frontend/src/hooks/`: reusable job, filter, profile, preferences, and saved-job state.
- `frontend/src/components/`: shared page layout, navigation, job cards/lists/filters, pagination, and UI primitives.
- `frontend/src/pages/`: Dashboard, Jobs, Job Discovery, Settings, Skills & Profile, plus Recommended Jobs, Applications, Resume Analyzer, Email & Responses, Agent Activity, and Login.
- `frontend/src/utils/`, `frontend/src/styles/`: job formatting/normalization and shared styling.
- Root `README.md`: CLI and local web-app setup. `netlify.toml` configures the frontend build/deploy; `frontend/vite.config.js` serves the dev app on port 8002.

## Main behavior and data flow

1. `python backend/Server/server.py` starts the API (default port 8001); CLI flags also allow fetching one or all sources, searching, sorting, limiting, and listing sources.
2. The backend runs portal connectors concurrently, normalizes results to a shared job record, emits progress/portal metadata, and writes JSON data for subsequent requests. The frontend can refresh or stop an active fetch.
3. The Jobs page filters and paginates results in the browser, shows portal notes/credits, and expands job details. Saved jobs are managed through `/api/saved`.
4. Firebase Auth guards the workspace routes (the standalone `/jobs` route is outside that guard). Firestore stores search preferences/API-key settings. Profile and resume helpers use backend `/api/profile` and `/api/resume`; resume upload accepts PDF, DOCX, and TXT for text extraction.
5. The API also exposes health, portal catalog, summary, stop-fetch, preferences, and authenticated `/api/ai/generate` endpoints. The AI helper verifies the Firebase ID token and obtains the user's Gemini key from Firestore.

**Integration note:** the frontend Settings preference helper talks directly to Firestore, while the backend also has `/api/preferences` endpoints and reads per-user preference JSON when fetching jobs. Check that these stores and flows are intentionally synchronized before changing preference behavior.

## Frontend route status

The live Jobs and Settings experiences have working data flows, and Skills & Profile is backed by the profile/resume API. Several other navigation destinations (notably Applications, Recommended Jobs, Resume Analyzer, Email & Responses, and Agent Activity) currently render informational/empty-state workspace pages with placeholder metrics rather than complete connected workflows.

## Local development and checks

- Backend API: `python backend/Server/server.py`
- Frontend: from `frontend/`, run `npm install`, then `npm run dev`.
- Frontend checks: `npm run lint` and `npm run build`.
- Backend tests: from `backend/`, run `python -m unittest`.
- Local configuration belongs in the ignored root `.env`; do not paste its values into documentation or commits. Frontend Firebase settings use `VITE_FIREBASE_*`; the API URL can be set with `VITE_JOBS_API_URL`.

## Handoff caution

At the time this guide was written, `frontend/src/pages/Settings/Settings.jsx` and `Settings.css` already had uncommitted changes. Preserve and build on those edits; do not revert or overwrite them when working on Settings.
