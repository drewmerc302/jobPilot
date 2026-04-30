// ─────────────────────────────────────────────────────────────────────────────
// jobPilot User Guide
// Build: typst compile user_guide.typ user_guide.pdf
//
// ADDING SCREENSHOTS
// Replace each placeholder() call with:
//   image("screenshots/XX-name.png", width: 100%)
// The filename for each section is shown inside the gray box.
// ─────────────────────────────────────────────────────────────────────────────

#let brand   = rgb("#0d6efd")
#let surface = rgb("#f8f9fa")
#let border  = rgb("#dee2e6")
#let muted   = rgb("#6c757d")
#let green   = rgb("#198754")
#let dark    = rgb("#212529")

// ── Helpers ──────────────────────────────────────────────────────────────────

#let placeholder(filename) = rect(
  width: 100%, height: 200pt,
  stroke: 1.5pt + border, fill: surface, radius: 4pt,
  align(center + horizon,
    stack(dir: ttb, spacing: 8pt,
      text(size: 22pt)["📸"],
      text(fill: muted, size: 9pt, font: "Courier New")[#filename],
    )
  )
)

#let callout(body) = rect(
  width: 100%, inset: 10pt,
  stroke: (left: 3pt + brand), fill: rgb("#e8f0fe"), radius: (right: 4pt),
  text(size: 10pt)[#body]
)

#let tip(body) = rect(
  width: 100%, inset: 10pt,
  stroke: (left: 3pt + green), fill: rgb("#e6f4ea"), radius: (right: 4pt),
  text(size: 10pt)[#body]
)

#let step-label(n) = box(
  width: 18pt, height: 18pt, radius: 9pt, fill: brand,
  align(center + horizon, text(fill: white, weight: "bold", size: 9pt)[#n])
)

#let steps(items) = {
  for (i, item) in items.enumerate() {
    grid(columns: (22pt, 1fr), gutter: 6pt,
      step-label(i + 1),
      align(horizon, text(size: 10.5pt)[#item]),
    )
    v(5pt)
  }
}

#let section-rule() = { v(4pt); line(length: 100%, stroke: 0.5pt + border); v(12pt) }

// ── Page setup ───────────────────────────────────────────────────────────────

#set page(
  paper: "us-letter",
  margin: (x: 52pt, y: 56pt),
  footer: context {
    let p = counter(page).get().first()
    if p > 1 {
      line(length: 100%, stroke: 0.5pt + border)
      v(3pt)
      grid(columns: (1fr, 1fr),
        text(fill: muted, size: 8pt)[jobPilot — User Guide],
        align(right, text(fill: muted, size: 8pt)[#p]),
      )
    }
  }
)

#set text(font: "Helvetica Neue", size: 11pt, fill: dark)
#set par(leading: 0.7em)
#show heading.where(level: 1): it => {
  v(18pt)
  text(size: 16pt, weight: "bold", fill: brand)[#it.body]
  v(2pt)
  line(length: 100%, stroke: 1.5pt + brand)
  v(10pt)
}
#show heading.where(level: 2): it => {
  v(14pt)
  text(size: 12pt, weight: "bold")[#it.body]
  v(6pt)
}
#show heading.where(level: 3): it => {
  v(10pt)
  text(size: 10.5pt, weight: "bold", fill: muted)[#it.body]
  v(4pt)
}

// ─────────────────────────────────────────────────────────────────────────────
// COVER
// ─────────────────────────────────────────────────────────────────────────────

#page(margin: (x: 0pt, y: 0pt))[
  #rect(width: 100%, height: 100%, fill: brand)[
    #align(center + horizon)[
      #stack(dir: ttb, spacing: 20pt,
        text(fill: white, size: 52pt, weight: "bold")[jobPilot],
        text(fill: rgb("#a8c7fa"), size: 15pt)[Your personal AI-powered job search assistant],
        v(10pt),
        rect(
          inset: (x: 20pt, y: 10pt),
          stroke: 1.5pt + white, radius: 30pt,
          text(fill: white, size: 11pt)[Getting Started Guide],
        ),
        v(40pt),
        text(fill: rgb("#a8c7fa"), size: 9pt)[Powered by Claude AI · Runs locally on your machine],
      )
    ]
  ]
]

// ─────────────────────────────────────────────────────────────────────────────
// TABLE OF CONTENTS
// ─────────────────────────────────────────────────────────────────────────────

#v(20pt)
#text(size: 18pt, weight: "bold")[Contents]
#v(8pt)
#line(length: 100%, stroke: 1.5pt + brand)
#v(10pt)

#let toc-row(num, title, desc) = {
  grid(columns: (18pt, 1fr),
    text(fill: brand, weight: "bold")[#num.],
    stack(dir: ttb, spacing: 2pt,
      text(weight: "bold")[#title],
      text(fill: muted, size: 9.5pt)[#desc],
    )
  )
  v(8pt)
}

#toc-row("1", "What is jobPilot?", "Overview and what you'll need before you start")
#toc-row("2", "First-Time Setup", "The five-step wizard: resume upload through your first search")
#toc-row("3", "Browsing Your Matches", "Reading match scores, navigating the list, keyboard shortcuts")
#toc-row("4", "Reviewing a Job", "Job detail page, generating a tailored resume, status tracking")
#toc-row("5", "Managing Your Resume", "Editing profile data, AI summary rewrite, adding experience")
#toc-row("6", "Settings", "API keys, search parameters, cost meter")
#toc-row("7", "Understanding Costs", "What each feature costs and how to monitor spend")
#toc-row("8", "Tips & Troubleshooting", "Common questions and how to get unstuck")

// ─────────────────────────────────────────────────────────────────────────────
// 1 — WHAT IS JOBPILOT?
// ─────────────────────────────────────────────────────────────────────────────

= 1. What is jobPilot?

jobPilot is a local application that runs on your computer and helps you find, evaluate, and apply to jobs — without the noise of generic job boards.

It connects to job listing APIs, scores each result against your actual resume using AI, and surfaces the roles most worth your time. When you find a promising match, one click generates a tailored resume analysis that tells you exactly how to position yourself for that specific role.

*Everything stays on your machine.* Your resume data never leaves your computer — the only outbound calls are to Anthropic (for AI features) and Adzuna (for job listings).

== What you'll need

#grid(columns: (1fr, 1fr), gutter: 12pt,
  rect(inset: 12pt, stroke: 1pt + border, radius: 4pt, width: 100%)[
    *Required*
    #v(6pt)
    #set text(size: 10pt)
    - Your resume (PDF or DOCX)
    - Anthropic API key\
      #text(fill: muted, size: 9pt)[console.anthropic.com]
    - Adzuna API key\
      #text(fill: muted, size: 9pt)[developer.adzuna.com — free tier]
  ],
  rect(inset: 12pt, stroke: 1pt + border, radius: 4pt, width: 100%)[
    *Nice to have*
    #v(6pt)
    #set text(size: 10pt)
    - A list of target companies
    - Your preferred job titles
    - Location / remote preference
    - Seniority level you're targeting
  ],
)

#v(10pt)
#callout[*New to Anthropic?* Create a free account at console.anthropic.com, add a small amount of credit (\$5–10 is plenty to start), and copy your API key from the API Keys section. jobPilot will show you a running cost total so you always know what you've spent.]

// ─────────────────────────────────────────────────────────────────────────────
// 2 — FIRST-TIME SETUP
// ─────────────────────────────────────────────────────────────────────────────

= 2. First-Time Setup

The first time you open jobPilot, a five-step wizard walks you through everything. You only need to do this once — your settings are saved and the app auto-refreshes job listings in the background from then on.

== Step 1 — Welcome

#placeholder("01-wizard-welcome.png")
#v(8pt)

The welcome screen explains what the wizard will do. Click *Get Started* to begin.

== Step 2 — Upload Your Resume

#placeholder("02-wizard-upload.png")
#v(8pt)

#steps((
  [Click the upload area or drag your resume file onto it. PDF and DOCX formats are supported (max 5 MB).],
  [Once the filename appears in green, the *Extract resume* button activates.],
  [Click *Extract resume*. Claude reads your file and pulls out your contact information, work history, skills, and summary. This usually takes 10–20 seconds.],
))

#tip[The more complete your resume, the better your match scores will be. If your resume is sparse in any area, you can fill in the gaps on the Resume page later (Section 5).]

== Step 3 — Review the Extraction

#placeholder("03-wizard-confirm.png")
#v(8pt)

jobPilot shows you what it extracted. Fields highlighted in yellow need your attention — they were low-confidence or missing.

#steps((
  [Check your name, email, phone, and location. Correct anything that looks wrong.],
  [Review the skills list. Add anything that's missing or remove things that aren't relevant.],
  [Your work experience is shown as a read-only preview here. You can edit it in detail later on the Resume page.],
  [Click *Looks good →* when you're satisfied.],
))

== Step 4 — Configure Your Search

#placeholder("04-wizard-search.png")
#v(8pt)

This is where you tell jobPilot what to look for.

#grid(columns: (1fr, 1fr), gutter: 12pt,
  stack(dir: ttb, spacing: 6pt,
    text(weight: "bold", size: 10.5pt)[Location],
    text(size: 10pt)[Enter your city or zip code and choose a search radius. Listings within that radius will be included.],
  ),
  stack(dir: ttb, spacing: 6pt,
    text(weight: "bold", size: 10.5pt)[Remote jobs],
    text(size: 10pt)[Off by default. Turn it on to include remote-eligible listings alongside local ones.],
  ),
  stack(dir: ttb, spacing: 6pt,
    text(weight: "bold", size: 10.5pt)[Keywords],
    text(size: 10pt)[Job titles or terms to match against listings. Each keyword is matched independently — shorter phrases cast a wider net.],
  ),
  stack(dir: ttb, spacing: 6pt,
    text(weight: "bold", size: 10.5pt)[Target companies],
    text(size: 10pt)[Companies you specifically want to work at. Use *Find similar companies* to let AI suggest additions based on your list.],
  ),
)

#v(10pt)
#callout[Keywords use OR logic and substring matching. "Engineering Manager" will match "Senior Engineering Manager", "Lead Engineering Manager", and so on. Start broad — you can tighten the filter later in Settings.]

== Step 5 — Your First Search

#placeholder("05-first-run.png")
#v(8pt)

jobPilot kicks off a search immediately. A progress indicator shows each stage as it runs (fetching listings, scoring matches, ranking results). This usually takes 1–3 minutes depending on result volume.

When it finishes, you're taken directly to your Matches list.

// ─────────────────────────────────────────────────────────────────────────────
// 3 — BROWSING YOUR MATCHES
// ─────────────────────────────────────────────────────────────────────────────

= 3. Browsing Your Matches

#placeholder("06-matches-list.png")
#v(8pt)

The Matches page is your home base. Every job jobPilot found is listed here, sorted by how well it fits your profile.

== Reading the list

Each row shows:

#grid(columns: (80pt, 1fr), gutter: 8pt,
  text(weight: "bold", size: 10pt)[Score],
  text(size: 10pt)[A percentage from 0–100 reflecting how closely the job matches your resume. 70+ is a strong match worth reviewing.],
  text(weight: "bold", size: 10pt)[Company & Title],
  text(size: 10pt)[Click anywhere on the row to open the full job detail.],
  text(weight: "bold", size: 10pt)[Location],
  text(size: 10pt)[City or "Remote". Listings with both an office and remote option may show the office city.],
  text(weight: "bold", size: 10pt)[Salary],
  text(size: 10pt)[Shown when the listing includes it. Many listings don't disclose salary.],
  text(weight: "bold", size: 10pt)[Status],
  text(size: 10pt)[Where you are in the application process for this role.],
)

== Keyboard shortcuts

You can navigate the list without touching your mouse:

#grid(columns: (60pt, 1fr), gutter: 6pt,
  ..for (key, action) in (
    ("j / ↓",    "Move to next job"),
    ("k / ↑",    "Move to previous job"),
    ("Enter / D","Open job details"),
    ("X",        "Dismiss this match"),
    ("?",        "Show all shortcuts"),
    ("Esc",      "Close / deselect"),
  ) { (
    rect(inset: (x: 5pt, y: 2pt), stroke: 0.5pt + border, radius: 3pt,
      text(size: 9pt, font: "Courier New")[#key]),
    align(horizon, text(size: 10pt)[#action]),
  )}
)

// ─────────────────────────────────────────────────────────────────────────────
// 4 — REVIEWING A JOB
// ─────────────────────────────────────────────────────────────────────────────

= 4. Reviewing a Job

== The job detail page

#placeholder("07-job-detail.png")
#v(8pt)

Click any row in the matches list to open the job detail page. You'll see the full job description (fetched directly from the source where possible), match score breakdown, and actions.

The *Application status* dropdown in the top-right tracks where you are with this role. Update it as you progress — the status is reflected in the matches list so you always have a clear picture of your pipeline.

== Generating a tailored resume analysis

#placeholder("08-tailor-modal.png")
#v(8pt)

Click *Generate Tailored Resume* to open the tailor panel. If the job hasn't been analyzed yet, the analysis starts automatically — no extra clicks needed.

The analysis produces three things:

#grid(columns: (110pt, 1fr), gutter: 8pt,
  text(weight: "bold", size: 10pt)[Key requirements],
  text(size: 10pt)[The most important things the employer is looking for, each rated as a strong match, partial match, or gap based on your resume.],
  text(weight: "bold", size: 10pt)[Suggested edits],
  text(size: 10pt)[Specific changes to your resume wording, ordering, or emphasis that would improve how you present for this role.],
  text(weight: "bold", size: 10pt)[Gap analysis],
  text(size: 10pt)[Skills or experience the job asks for that aren't well-represented in your resume — useful for deciding what to address in a cover letter.],
)

#v(10pt)
#callout[*Re-analyze* is available if the job description was updated or you've edited your resume since the last analysis. Each analysis costs roughly \$0.05–0.10 via the Anthropic API.]

// ─────────────────────────────────────────────────────────────────────────────
// 5 — MANAGING YOUR RESUME
// ─────────────────────────────────────────────────────────────────────────────

= 5. Managing Your Resume

#placeholder("09-resume-editor.png")
#v(8pt)

The *Resume* page (accessible from the nav bar) lets you view and edit every piece of data jobPilot knows about you. Changes you make here are reflected immediately in all future match scoring and tailoring.

== Sections

*Contact* — Name, title, email, phone, location, LinkedIn, GitHub, and website.

*Professional Summary* — Your career summary. Edit it directly, or use the AI rewrite helper.

*Skills* — One skill per line. Edit freely — add, remove, or reword anything. The full list is used in match scoring.

*Experience* — Your work history, broken into companies and positions. Each position has a title, dates, and achievement bullets (one per line).

*Education* — Institution, degree, and graduation year for each entry.

== AI summary rewrite

Expand the *✦ AI rewrite help* panel under the Summary section. Describe your recent accomplishments in plain language — specific numbers and outcomes work best — and click *Suggest summary*. Claude drafts an improved 2–5 sentence summary. Click *Use this* to apply it, or *Discard* to ignore it.

#tip[Be specific: "Led payments platform that launched Apple in-app purchases, generating \$26M in first 6 months" produces much better results than "Managed a payments team".]

== Adding new experience

The *Add new experience* card at the bottom accepts freeform text. Describe a role in plain language — company, title, dates, and what you did — and Claude structures it into the correct format when you save. No need to worry about formatting.

// ─────────────────────────────────────────────────────────────────────────────
// 6 — SETTINGS
// ─────────────────────────────────────────────────────────────────────────────

= 6. Settings

#placeholder("10-settings.png")
#v(8pt)

The Settings page covers two areas:

== API keys

Enter your Anthropic and Adzuna credentials here. These are stored locally in `~/.jobpilot/` and never transmitted anywhere except the respective APIs.

== Search parameters

Update your location, radius, keywords, seniority filter, remote preference, and target company list at any time. Changes take effect on the next search run.

You can also trigger a manual refresh from this page without waiting for the 12-hour auto-refresh cycle.

// ─────────────────────────────────────────────────────────────────────────────
// 7 — UNDERSTANDING COSTS
// ─────────────────────────────────────────────────────────────────────────────

= 7. Understanding Costs

jobPilot uses your Anthropic API key directly. You pay Anthropic; jobPilot itself has no subscription fee.

#rect(width: 100%, inset: 12pt, stroke: 1pt + border, radius: 4pt)[
  #grid(columns: (1fr, 80pt, 1fr), gutter: 0pt,
    text(weight: "bold", size: 10pt)[Feature],
    align(center, text(weight: "bold", size: 10pt)[Approx. cost]),
    text(weight: "bold", size: 10pt)[When it runs],
  )
  #line(length: 100%, stroke: 0.5pt + border)
  #v(4pt)
  #let row(feat, cost, when) = {
    grid(columns: (1fr, 80pt, 1fr), gutter: 0pt,
      text(size: 10pt)[#feat],
      align(center, text(size: 10pt, fill: brand)[#cost]),
      text(size: 10pt, fill: muted)[#when],
    )
    v(5pt)
  }
  #row("Resume extraction",        "~\$0.05",       "Once, during setup")
  #row("Match scoring (per run)",  "~\$0.01–0.03",  "Every 12 hrs (auto) or on-demand")
  #row("Tailor analysis (per job)","~\$0.05–0.10",  "When you click Generate")
  #row("AI summary rewrite",       "~\$0.03",       "When you click Suggest summary")
  #row("New experience parse",     "~\$0.01",       "When you save new experience text")
]

#v(10pt)

The *cost meter* in the top-right nav bar shows your running total for the current session. Check the Settings page for cumulative spend.

#callout[A \$10 Anthropic credit will cover several weeks of normal use — roughly 5–10 search runs plus 20–30 tailor analyses.]

// ─────────────────────────────────────────────────────────────────────────────
// 8 — TIPS & TROUBLESHOOTING
// ─────────────────────────────────────────────────────────────────────────────

= 8. Tips & Troubleshooting

== Getting better matches

- *Shorter keywords beat longer ones.* "Engineering Manager" returns more results than "Senior Engineering Manager, Platform."
- *Add target companies.* Even a short list meaningfully improves ranking — the scorer gives a boost to roles at companies you care about.
- *Keep your resume current.* Match scoring runs against whatever's in your profile. If you've updated your skills or changed roles, update your Resume page first.

== Navigating back to the wizard

If you want to re-run the wizard (for example, to re-upload a new resume version), navigate directly to `http://127.0.0.1:8765/wizard/step/0`. To start completely fresh, delete `~/.jobpilot/profile.json` before visiting that URL.

== The app isn't opening

jobPilot runs on port 8765. If the browser doesn't open automatically, navigate to `http://127.0.0.1:8765` manually. If the page doesn't load, check that the app process is running (look for the jobPilot icon in your system tray / menu bar).

== "No matches found"

If a search returns nothing, try broadening your keywords (remove seniority prefixes, use shorter phrases) or increasing your search radius. You can also check Settings to confirm your Adzuna credentials are valid.

== API errors

All API errors are shown inline. If you see a message about an invalid key, double-check your credentials in Settings. If calls are failing intermittently, it's usually a temporary issue with the upstream API — the next auto-refresh will retry.

#v(30pt)
#align(center)[
  #text(fill: muted, size: 9pt)[jobPilot · github.com/drewmerc302/jobPilot · MIT License]
]
