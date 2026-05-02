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

### Job detail analysis
Every job detail page shows an AI breakdown of the role against your profile: why it fits, the key requirements extracted from the description, and interview talking points specific to your background.

### Resume tailoring
Click **Generate Tailored Resume** on any job. Claude produces a diff of your resume bullets — current vs. suggested rewrites with a rationale for each change. Check the edits you want to apply, then click **Generate PDF** to produce a tailored resume ready to send. Your stored profile is unchanged.

### Interview Q&A Guide
One click generates a set of likely interview questions for the role with suggested answers drawn from your specific experience. Available on every job detail page (~$0.03).

### Resume editor
The **Resume** page lets you edit your stored profile directly — the data that drives all matching and tailoring:
- Add new experience in plain language at the top; Claude structures it automatically on save
- Edit contact info, summary, skills, and structured work history
- AI summary rewrite: describe your recent accomplishments, get a polished 2–5 sentence draft

### Application tracking
Track each role through your pipeline via the status dropdown on the job detail page (New → Applied → Interviewing → Offer → Rejected).

### Contextual tooltips
Hover over any button, column header, or form label to get a plain-language explanation of what it does and what it costs.

## Documentation

A full annotated user guide is available at [`docs/user_guide/`](docs/user_guide/). Build the PDF locally:

```bash
cd docs/user_guide
typst compile user_guide.typ user_guide.pdf
```

Requires [Typst](https://typst.app). The source references screenshots from `screenshots/` (gitignored — see [`SHOT_LIST.md`](docs/user_guide/SHOT_LIST.md) for what to capture).

## Packaging

jobPilot uses [Briefcase](https://briefcase.readthedocs.io/) for native packaging.

### Vendored Typst binaries

Resume PDF generation uses [Typst](https://typst.app). Binaries are vendored at build time (~40 MB each, gitignored) into `src/jobpilot/resources/typst/<arch>/`. Run once before building or developing:

```bash
# All four targets (arm64+x86_64 macOS, linux, windows):
python scripts/fetch_typst.py

# Just the host arch (faster for dev):
python scripts/fetch_typst.py --current
```

The bash (`scripts/fetch_typst.sh`) and PowerShell (`scripts/fetch_typst.ps1`) wrappers do the same thing.

**macOS:**
```bash
briefcase build macOS
briefcase run macOS
```

`universal_build = false` in `pyproject.toml` — produce one bundle per host arch and ship both, or set `true` if you have an `arm64+x86_64` Python.

**Windows** — requires a Windows machine or CI. See [`docs/WINDOWS_BUILD.md`](docs/WINDOWS_BUILD.md) for full instructions including a ready-to-use GitHub Actions workflow.

## Cost

All AI features use your Anthropic API key and are billed to your account. Rough estimates:
- Resume extraction (one-time): ~$0.05
- Match scoring per run: ~$0.01–0.03 depending on result count
- Tailor analysis + resume PDF per job: ~$0.03
- Interview Q&A Guide per job: ~$0.03
- AI summary rewrite: ~$0.03
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
