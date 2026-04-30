# jobPilot

A local-first job search tool that finds, ranks, and tailors job matches using your resume and Claude AI. Runs entirely on your machine — your resume data never leaves your computer.

## What it does

- **Pulls job listings** from Adzuna (and optionally other boards) based on your search criteria
- **Scores and ranks matches** against your resume using AI, surfacing the jobs most worth your time
- **Tailors your resume** for a specific role with one click — highlights relevant experience, flags gaps, suggests edits
- **Tracks applications** with a lightweight status tracker (New → Applied → Interviewing → Offer → Rejected)
- **Edits your resume in-place** — update contact info, summary, skills, and experience without leaving the app, with an AI-assisted summary rewrite helper

## How it works

jobPilot runs a local FastAPI server and opens in your browser. A system tray icon keeps it running in the background and auto-refreshes job listings every 12 hours.

All data — your resume, job listings, match scores — lives in `~/.jobpilot/` on your machine. LLM calls go directly to the Anthropic API using your own key.

## Setup

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)
- An [Adzuna API key](https://developer.adzuna.com/) (free tier works)

### Install

```bash
git clone https://github.com/drewmerc302/jobPilot.git
cd jobPilot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### Configure

Create `~/.jobpilot/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
ADZUNA_APP_ID=your_app_id
ADZUNA_APP_KEY=your_app_key
```

### Run

```bash
python -m jobpilot
```

The app opens in your browser at `http://127.0.0.1:8765`. On first launch, a setup wizard walks you through uploading your resume and configuring your search.

## First run

1. **Upload your resume** — PDF or DOCX. Claude extracts your experience, skills, and contact info.
2. **Confirm the extraction** — review and correct anything that looks off.
3. **Set up your search** — location, radius, keywords, target companies.
4. **Get your first matches** — ranked by fit, ready to review.

## Features

### Job matching
Jobs are scored against your resume on relevance, seniority fit, and keyword overlap. The matches list shows score, company, title, salary, and location at a glance.

### Resume tailoring
Open any job and click **Generate Tailored Resume**. Claude analyzes the job description against your profile and returns:
- Key requirements and how well you match each
- Suggested resume edits specific to this role
- A gap analysis — skills or experience worth addressing in a cover letter

### Resume editor
The **Resume** page (`/profile`) lets you edit your stored resume data directly:
- Update contact info, summary, skills, and structured experience
- AI summary rewrite: describe your recent accomplishments, get a polished 2–5 sentence summary
- Add new experience in plain language — Claude structures it into the correct format on save

### Application tracking
Track application status per job. The status dropdown on each job detail page moves a listing through your pipeline.

## Packaging

jobPilot uses [Briefcase](https://briefcase.readthedocs.io/) for native packaging.

**macOS:**
```bash
briefcase build macOS
briefcase run macOS
```

**Windows** — requires a Windows machine or CI. See [`docs/WINDOWS_BUILD.md`](docs/WINDOWS_BUILD.md) for full instructions including a ready-to-use GitHub Actions workflow.

## Cost

All AI features use your Anthropic API key and are billed to your account. Rough estimates:
- Resume extraction (one-time): ~$0.05
- Match scoring per run: ~$0.01–0.03 depending on result count
- Tailor analysis per job: ~$0.05–0.10
- Summary rewrite: ~$0.03
- New experience parse: ~$0.01

A cost meter in the nav bar shows your running total.

## Tech stack

- **Backend:** FastAPI + uvicorn
- **Frontend:** Jinja2 templates + HTMX (no build step)
- **Database:** SQLite
- **AI:** Anthropic Claude (Sonnet for tailoring/summaries, Haiku for extraction)
- **Job data:** Adzuna API
- **Packaging:** Briefcase (macOS app bundle, Windows MSI)
- **System tray:** pystray + Pillow

## Data & privacy

Everything stays local. Your resume is stored in `~/.jobpilot/profile.json`. Job listings are cached in `~/.jobpilot/jobpilot.db`. The only outbound calls are to the Anthropic API (for AI features) and Adzuna (for job listings).

## License

MIT
