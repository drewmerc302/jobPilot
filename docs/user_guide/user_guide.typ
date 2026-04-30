// ─────────────────────────────────────────────────────────────────────────────
// jobPilot User Guide
// Build: typst compile user_guide.typ user_guide.pdf
// ─────────────────────────────────────────────────────────────────────────────

#let brand   = rgb("#0d6efd")
#let surface = rgb("#f8f9fa")
#let border  = rgb("#dee2e6")
#let muted   = rgb("#6c757d")
#let green   = rgb("#198754")
#let dark    = rgb("#212529")

// ── Helpers ──────────────────────────────────────────────────────────────────

#let shot(file, height: none) = {
  if height != none {
    box(width: 100%, height: height, clip: true,
      image("screenshots/" + file, width: 100%)
    )
  } else {
    image("screenshots/" + file, width: 100%)
  }
  rect(width: 100%, height: 0.5pt, fill: border)
}

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

#let label-row(items) = {
  for (key, val) in items {
    grid(columns: (110pt, 1fr), gutter: 8pt,
      text(weight: "bold", size: 10pt)[#key],
      text(size: 10pt)[#val],
    )
    v(5pt)
  }
}

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
#toc-row("4", "Reviewing a Job", "Job detail page, AI analysis, tailored resume, interview prep")
#toc-row("5", "Managing Your Resume", "Editing profile data, AI summary rewrite, adding experience")
#toc-row("6", "Settings", "API key, spending limit, and monthly budget")
#toc-row("7", "Understanding Costs", "What each feature costs and how to monitor spend")
#toc-row("8", "Tips & Troubleshooting", "Common questions and how to get unstuck")

// ─────────────────────────────────────────────────────────────────────────────
// 1 — WHAT IS JOBPILOT?
// ─────────────────────────────────────────────────────────────────────────────

= 1. What is jobPilot?

jobPilot is a local application that runs on your computer and helps you find, evaluate, and apply to jobs — without the noise of generic job boards.

It connects to job listing APIs, scores each result against your actual resume using AI, and surfaces the roles most worth your time. When you find a promising match, one click generates a tailored resume analysis telling you exactly how to position yourself — and produces an edited resume PDF ready to send.

*Everything stays on your machine.* Your resume data never leaves your computer. The only outbound calls are to Anthropic (for AI features) and Adzuna (for job listings).

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
#callout[*New to Anthropic?* Create a free account at console.anthropic.com, add a small amount of credit (\$5–10 is plenty to start), and copy your API key from the API Keys section. The cost meter in the top-right corner of jobPilot always shows your running total.]

// ─────────────────────────────────────────────────────────────────────────────
// 2 — FIRST-TIME SETUP
// ─────────────────────────────────────────────────────────────────────────────

= 2. First-Time Setup

The first time you open jobPilot, a five-step wizard walks you through everything. Progress dots at the top of the screen track where you are. You only need to do this once — your settings are saved and the app auto-refreshes job listings in the background from then on.

== Step 1 — Welcome

#shot("01-wizard-welcome.png")
#v(8pt)

The welcome screen outlines the four things the wizard will do. Click *Get Started →* to begin.

== Step 2 — Upload Your Resume

#shot("02-wizard-upload.png")
#v(8pt)

#steps((
  [Click the upload area or drag your resume file onto it. PDF and DOCX are supported (max 5 MB).],
  [Once a filename appears, the *Extract resume* button activates.],
  [Click *Extract resume*. Claude reads your file and pulls out your contact information, work history, skills, and summary. This usually takes 10–20 seconds.],
))

== Step 3 — Review the Extraction

#shot("03-wizard-confirm.png")
#v(8pt)

jobPilot shows you what Claude extracted. Review everything before continuing.

#steps((
  [Check your name, email, phone, and location. Correct anything that looks wrong.],
  [Review the *Professional summary* — edit it directly if needed.],
  [Check the *Skills* list. Add anything missing or remove things that aren't relevant to your search.],
  [Your work experience is shown as a read-only preview. You can edit each role in detail later on the Resume page.],
  [Click *Looks good →* when satisfied, or *Re-upload* to start over with a different file.],
))

== Step 4 — Configure Your Search

#shot("04-wizard-search.png")
#v(8pt)

#label-row((
  ("Location",          "Your city or zip code. Set a search radius (miles) to control how far out listings are pulled."),
  ("Remote jobs",       "Off by default. Check this to include remote-eligible listings alongside local results."),
  ("Keywords",          "Job titles or terms matched independently against listing titles (OR logic, case-insensitive). Shorter phrases return more results."),
  ("Seniority filter",  "Narrows results to a specific level. Leave blank to see all levels."),
  ("Target companies",  "Companies you specifically want to work at. Use Find similar companies to let AI expand the list based on what you enter."),
))

#v(6pt)
#callout["Engineering Manager" matches "Senior Engineering Manager", "Lead Engineering Manager", and more. Start broad — you can tighten the filter after seeing your first results.]

== Step 5 — Your First Search

#shot("05-first-run.png")
#v(8pt)

jobPilot kicks off a search immediately. When it finishes, the screen shows a summary: how many new jobs were found, how many scored as matches, and how long it took. Click *View matches →* to see your results.

#tip[The first run after setup may return fewer results than later runs — the scraper builds up its cache over time. The app auto-refreshes every 12 hours so your list grows with each cycle.]

// ─────────────────────────────────────────────────────────────────────────────
// 3 — BROWSING YOUR MATCHES
// ─────────────────────────────────────────────────────────────────────────────

= 3. Browsing Your Matches

#shot("06-matches-list.png", height: 340pt)
#v(8pt)

The Matches page is your home base. Every job jobPilot found is listed here, sorted by how well it fits your profile. The search summary bar at the top shows your active keywords, location, and filters — click *Edit search* to adjust them at any time.

== Reading the list

#label-row((
  ("Score",           "A percentage reflecting how closely the job matches your resume. 70%+ is worth a close look."),
  ("Why it fits",     "A one-paragraph AI summary explaining the match — read this first before clicking into a job."),
  ("Salary",          "Shown when the listing includes it. Many postings don't disclose salary upfront."),
  ("Status",          "Where you are in the application process. Update it as you progress."),
  ("Tailored resume ↗", "Appears in green when a tailored resume has already been generated for this job."),
))

== Adding your own listing

Use *+ Add your own job listing* to paste in a role you found elsewhere. jobPilot will score and analyze it the same way as scraped listings.

== Keyboard shortcuts

#grid(columns: (70pt, 1fr), gutter: 6pt,
  ..for (key, action) in (
    ("j / ↓",     "Move to next job"),
    ("k / ↑",     "Move to previous job"),
    ("Enter / D", "Open job details"),
    ("X",         "Dismiss this match"),
    ("?",         "Show all shortcuts"),
    ("Esc",       "Close / deselect"),
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

#shot("07-job-detail.png", height: 380pt)
#v(8pt)

Click any row in the matches list to open the job detail page. The main panel shows three AI-generated sections:

#label-row((
  ("Why it fits",              "A narrative explanation of why this role matches your background specifically."),
  ("Key requirements",         "The most important things the employer is asking for, extracted from the job description."),
  ("Interview talking points", "Specific angles to emphasize when interviewing — drawn from your resume and the job's priorities."),
))

The right sidebar holds the action panel:

- *Application status* — track this role through your pipeline (New → Applied → Interviewing → Offer → Rejected)
- *Re-analyze* — re-run the AI analysis after you've updated your resume or if the job description changed (~\$0.03)
- *Generate Tailored Resume* — opens the resume edit modal (see below)
- *Interview Q&A Guide* — generates a set of likely interview questions with suggested answers tailored to this role (~\$0.03)

== Generating a tailored resume

Clicking *Generate Tailored Resume* opens a modal. If this job hasn't been analyzed yet, the analysis starts automatically — no extra clicks.

*Step 1 — Analysis runs:*

#shot("08-tailor-loading.png")
#v(8pt)

A spinner confirms the analysis is in progress. This takes 20–40 seconds and costs roughly \$0.03 via Claude.

*Step 2 — Review and select edits:*

#shot("08-tailor-results.png", height: 400pt)
#v(8pt)

Once complete, the modal shows a side-by-side diff of your resume bullets. For each suggested change you'll see:

#label-row((
  ("Current",   "Your existing resume bullet, shown with strikethrough."),
  ("Suggested", "The AI-proposed rewrite, shown in green. Language is tightened and aligned to the job's specific terminology."),
  ("Rationale", "A one-line explanation of why this edit improves your fit for this role."),
))

Use the checkboxes to select which edits to apply. *Select all* / *Deselect all* controls let you accept or review everything in bulk. When you're satisfied, click *Generate PDF* to produce a tailored resume PDF with your selected edits applied.

#callout[Bullets are always reordered by relevance to the role — even unchecked edits benefit from the reordering. The PDF is the deliverable; your stored resume profile is unchanged.]

// ─────────────────────────────────────────────────────────────────────────────
// 5 — MANAGING YOUR RESUME
// ─────────────────────────────────────────────────────────────────────────────

= 5. Managing Your Resume

The *Resume* page (accessible from the nav bar) lets you view and edit every piece of data jobPilot knows about you. Changes save to your local profile and apply to all future match scoring and tailoring runs.

== Contact, summary, and skills

#shot("09-resume-top.png", height: 360pt)
#v(8pt)

The top of the page covers three sections:

*Contact* — Name, professional title, email, phone, location, LinkedIn, GitHub, and website. Keep these current so generated PDFs always have accurate headers.

*Professional Summary* — Edit directly, or use the *✦ AI rewrite help* panel. Expand it, describe your recent accomplishments in plain language (specific numbers and outcomes work best), and click *Suggest summary*. Claude drafts an improved 2–5 sentence version. Click *Use this* to apply it or *Discard* to ignore it.

*Skills* — One skill per line. Add, remove, or reword freely. This list feeds directly into match scoring — the more accurate it is, the better your results.

== Experience, education, and adding new roles

#shot("09-resume-bottom.png")
#v(8pt)

The lower sections cover your work history and education, plus a fast-entry path for new roles:

*Experience* — Each company and position is fully editable. Achievements are stored one per line — edit them directly to sharpen your bullets between applications.

*Education* — Institution, degree, and graduation year for each entry.

*Add new experience* — Describe a role in plain language and Claude structures it into the correct format automatically when you save. No need to worry about field names or formatting.

#tip[Be specific when adding experience: "Led payments platform that launched Apple in-app purchases, generating \$26M in first 6 months" produces much better bullets than "Managed a payments team".]

// ─────────────────────────────────────────────────────────────────────────────
// 6 — SETTINGS
// ─────────────────────────────────────────────────────────────────────────────

= 6. Settings

#shot("10-settings.png")
#v(8pt)

The Settings page has two controls:

*Anthropic API key* — Paste your key here. jobPilot stores it locally and never transmits it anywhere except the Anthropic API. Use the *Test key* button to verify it's valid before saving.

*Spending limit* — Set a monthly budget between \$0.50 and \$50.00. jobPilot will warn you when you approach this limit. The default is \$5.00/month — enough for weeks of normal use.

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
  #row("Resume extraction",           "~\$0.05",       "Once, during setup")
  #row("Match scoring (per run)",      "~\$0.01–0.03",  "Every 12 hrs (auto) or on-demand")
  #row("Tailor analysis (per job)",    "~\$0.03",       "When Generate Tailored Resume is clicked")
  #row("Interview Q&A Guide",          "~\$0.03",       "When Interview Q&A Guide is clicked")
  #row("AI summary rewrite",           "~\$0.03",       "When Suggest summary is clicked")
  #row("New experience parse",         "~\$0.01",       "When new experience text is saved")
]

#v(10pt)

The *cost meter* in the top-right nav bar (e.g. *\$0.21 / \$5.00 this month*) shows your running spend against your monthly budget at a glance.

#callout[A \$10 Anthropic credit covers several weeks of normal use — roughly 5–10 search runs plus 20–30 tailor analyses and interview guides.]

// ─────────────────────────────────────────────────────────────────────────────
// 8 — TIPS & TROUBLESHOOTING
// ─────────────────────────────────────────────────────────────────────────────

= 8. Tips & Troubleshooting

== Getting better matches

- *Shorter keywords beat longer ones.* "Engineering Manager" returns more results than "Senior Engineering Manager, Platform."
- *Add target companies.* Even a short list meaningfully improves ranking — the scorer gives a boost to roles at companies you care about. Use *Find similar companies* to expand it with AI suggestions.
- *Keep your resume current.* Match scoring runs against whatever's in your profile. Update your Resume page before running a fresh search.

== Re-running the wizard

To revisit any setup step, navigate directly to `http://127.0.0.1:8765/wizard/step/0`. To start completely fresh (re-upload a new resume), delete `~/.jobpilot/profile.json` before visiting that URL.

== The app isn't opening

jobPilot runs on port 8765. If the browser doesn't open automatically, navigate to `http://127.0.0.1:8765` manually. If the page doesn't load, check that the app process is running — look for the jobPilot icon in your system tray or menu bar.

== "No matches found"

Try broadening your keywords (remove seniority prefixes, use shorter phrases) or increasing your search radius. You can also click *Refresh* on the Matches page to trigger an immediate re-scan.

== API errors

All API errors are shown inline. If you see an invalid key message, double-check your credentials in Settings and use the *Test key* button. Intermittent failures are usually temporary upstream issues — the next auto-refresh will retry automatically.

#v(30pt)
#align(center)[
  #text(fill: muted, size: 9pt)[jobPilot · github.com/drewmerc302/jobPilot · MIT License]
]
