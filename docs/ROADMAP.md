# jobPilot Roadmap

**Last updated:** 2026-04-29
**Status:** Phase 0 complete. Phase 1 (Adzuna aggregator scraper) is next.

---

## What jobPilot is

A productionalized fork of `~/workspace/jobTracker/` (Drew's personal LLM-assisted job-search tool) built for non-technical friends to use for their own job searches. Friend-favor scope, not commercial.

**Audience:** Non-technical users in arbitrary fields. Friend survey (n=4): 2 Windows, 1 Linux, 1 Mac, all click-an-icon users. Fields represented: psych nurse, chemical engineer, doc review lawyer, kitchen mgmt.

**Core promise:** Double-click an app icon → walk through a 5-minute wizard → see ranked job matches with one-click resume tailoring.

**Architecture (proven by the Briefcase spike):** FastAPI server in a thread inside a Briefcase-packaged native app. `webbrowser.open()` to localhost. No native GUI code. Same packaging commands target macOS / Windows / Linux.

**jobTracker stays untouched.** Drew continues to use it for his own active EM job search. Useful pieces (LLM tool schemas, prompts, Greenhouse scraper, DB schema, Typst template) are *copied and adapted* into jobPilot, not imported.

---

## Settled decisions (with rationale)

### 1. LLM auth: BYO Anthropic API key with Drew-funded gift balance

**Decision:** Each friend's bundle ships with an embedded Anthropic API key tied to a per-friend $10-capped Anthropic workspace. They never see the words "API key" during onboarding. When they burn through the gift balance, they're prompted to paste their own key.

**Why we ruled out Pro/Max subscription:**
- Headless auth inside a Briefcase bundle is brutal — `claude` CLI auth requires interactive OAuth, no env-var equivalent. Inside a packaged `.app`/`.msi`/AppImage with no Terminal access, this means either bundling Claude Code CLI and rigging up browser-based auth from FastAPI (huge fragile undertaking), or telling a non-technical user to open Terminal — which is the exact thing jobPilot exists to avoid.
- No `tool_choice` equivalent in `claude -p` → structured outputs degrade to prompt-and-retry, putting JSON parse failures on a user who can't read a stack trace.
- Daily token budgets create a worse failure mode than prepaid credit ("come back tomorrow" vs clean exhaustion message + spend cap).
- Reality check: of 4 friends surveyed, ~zero already subscribe to Pro/Max. The "they're already paying" premise doesn't hold.

**Why we considered Pro/Max anyway:** Drew flagged a real point — Pro/Max is a *gateway purchase*. "I bought Claude and now have it everywhere" is a better narrative than "I bought tokens that only work in this one app." Honored as a sidebar in the wizard copy ("BTW Claude Pro is a separate thing if you want chat/desktop access — totally optional"). Not as the primary auth path.

**Why $10 gift balance:**
- Typical first run: ~$0.22
- Typical week of usage: ~$0.50
- $10 lasts ~5 months at typical usage, ~2 months at heavy usage
- Per-friend onboarding cost to Drew: ~$0.05 max (resume extraction + discovery only). Pre-onboarding spend on Drew's key for 5 friends: ~$0.25.
- Per-friend max liability if key leaks: $10 (capped at workspace level)

### 2. Distribution: Briefcase bundles, double-click to launch

`.app`/`.dmg` for macOS, `.msi` for Windows, AppImage for Linux. No CLI install. No pipx. No "open Terminal and run X." The Briefcase spike (commit `8195376`) verified end-to-end on macOS with FastAPI + vendored Typst + adhoc-signed `.dmg`.

### 3. Job sources: aggregator APIs first, Greenhouse retained

Adzuna (free baseline, ~250 calls/mo per key) + JSearch (paid upgrade tier, optional). Greenhouse retained for tech-friendly users who want to name specific companies. All other jobTracker scrapers (Apple, Google, Workday, Fidelity, Shopify) dropped — brittle, company-specific, against the "arbitrary fields" thesis.

### 4. Resume handling: PDF/DOCX import required, scratch-build out of scope

All four surveyed friends already have a resume. Wizard step 1 is "drop your resume file." The `resume-skills:extracting-resumes` skill prompts/schemas get *ported* (not invoked via subprocess) into the jobPilot codebase running through the Anthropic SDK directly.

Confirmation step shows extracted data as a structured form (editable name/jobs/skills/education), never raw YAML. Confidence-flagged fields highlight uncertainty. Paste-text fallback for image PDFs / two-column Canva layouts. OCR via Claude vision for scanned PDFs.

Resume version management (Drew's `v7 ai_workflow_story` system) is out of scope. One active resume per user.

### 5. Application status tracking: jobPilot owns the funnel

**Decision:** v1 owns simple status tracking. Looking at 75 jobs and not knowing what you've already applied to is too frustrating to defer.

**Status set:** `interested` / `applied` / `interviewing` / `offer` / `rejected` / `withdrawn`. (`ghosted` deferred to v1.x.) Anything more granular ("phone screen done," "onsite scheduled") goes in a free-form `notes` field.

**Schema port:** jobTracker's `applications` and `status_history` tables port directly. Drop the Drew-specific `salary_notes` column, replace with generic `notes` TEXT. Keep `follow_up_after`/`followed_up_at` columns even though the surfacing UI is deferred to v1.x — cheap to keep, expensive to retrofit.

### 6. Notification model: open-app refresh + capped manual refresh

**Decision:**
- Auto-refresh on app open if >12h since last run
- Manual refresh button capped at 3-5/day
- No OS-level notifications
- Per-run summary toast: "Refresh complete. 12 new jobs, 3 new matches, $0.04 spent."

**Why no OS notifications:** Briefcase native notifications are per-platform code, and the use case (jobPilot must be open to refresh anyway) doesn't justify the complexity. v1.x consideration if users ask.

### 7. Cost defenses

- **Cache filter results per `(job_id, resume_hash)`.** Re-runs are free for already-scored jobs. Resume edits invalidate the cache (correct: old scores are stale).
- **Running cost in app chrome.** `$1.23 / $10 this month` top-right corner. Real-time. People moderate naturally when they see a meter.
- **Cost on the tailor button.** `Tailor (~$0.03)` — informed choices.
- **Pathological-search warning.** If aggregator returns >500 results: "This will cost ~$0.22. Continue?"
- **Hard monthly spend cap.** Default $5, max $50, configurable on BYO. Pre-filter check blocks runs that would exceed cap.

### 8. Interview prep included in v1

**What it is (and isn't):** A single Sonnet call that takes job description + user's resume YAML and returns structured prep content: predicted likely questions, STAR-format stories mapping resume bullets to predicted questions, talking points, and gap/red-flag warnings to prepare for. Optionally augmented with a Wikipedia summary of the company for context.

**Critically: this is not Glassdoor or Levels.fyi scraping.** No external "real reported questions" data is fetched. The Sonnet model *predicts* questions from the JD + resume — that's the entire mechanism. Wikipedia REST API is the only outbound call and it's free, unauthenticated, and optional.

**Cost:** ~2500 input tokens + ~1500 output tokens at Sonnet pricing ≈ **$0.03/call**. Same order of magnitude as a tailor call. Fits the cost framework already in place.

**Why "cheap port":**
- Tool schema (`PREP_TOOL` in jobTracker's `interview_prep.py`) and prompt copy-paste with one parameterization (replace hardcoded "engineering manager candidate" with user's most recent role)
- Wikipedia fetch: ~10 lines, no auth, no scraping
- Rendering: ship as in-app HTML view first (no Typst required for v1). "Download as PDF" deferred to v1.x via existing Typst pipeline.
- Estimated work: ~half day

**UI:** Button on job-detail screen labeled `Generate Interview Prep (~$0.03)`. Cost-per-action labeling consistent with the cost-defense framework. Output rendered as a styled web view with sections for talking points, predicted questions with STAR stories collapsed under each, and red flags.

### 9. Drop or defer from jobTracker

| Component | Decision | Rationale |
|---|---|---|
| Obsidian integration | Drop | Drew-specific, ~zero target users have Obsidian |
| SMTP digest | Drop | App-password setup is exactly the friction jobPilot exists to remove. Replace with in-app toasts. |
| launchd / cron scheduling | Drop | Non-technical users can't configure. Replace with on-demand refresh; add in-app scheduler in v1.x. |
| Apple/Google/Workday/Fidelity/Shopify scrapers | Drop | Brittle, company-specific, against aggregator-first thesis |
| Gripes (Glassdoor scraping) | Defer to v1.x | Brittle, requires Playwright bundle bloat, squishy value for non-tech users |
| Interview prep | **Include in v1** | Pure LLM inference (not scraping). ~$0.03/call. Half-day port. See section 8 above. |
| On-demand Sonnet job analysis (`--show-job`) | Defer to v1.x | Useful but on-demand-by-button, not core daily flow |
| Cover letter generation | Defer to v2 | Already in skip list |
| Salary research as a discrete feature | Drop | Levels.fyi has no public API, Glassdoor blocks scraping. Surface salary ranges from job postings only (~30% of postings include them). |
| Multi-tenant hosting / accounts / billing | Out of scope | Friend-favor only |

---

## FTUE design (settled)

Wizard pattern: **value-first reordering with embedded gift balance.** No "API key" step during onboarding. Five steps:

**Step 0 — Welcome.** One screen. Sets expectations: "We need your resume, a few details, and we'll provide a starter Anthropic credit." Single "Get Started" button.

**Step 1 — Resume upload.** Drag-drop PDF/DOCX. Paste-text fallback link. Submit triggers extraction with a friendly progress message ("Reading your resume... Found work history... Found skills...").

**Step 2 — Confirm extracted resume.** Structured form, not YAML. Editable fields, confidence-flagged uncertain ones. **First wow moment.**

**Step 3 — Search setup with discovery.** Single screen with three sub-sections:
- Where you live + commute radius + remote-OK toggle
- Keywords (pre-filled from most recent role) + seniority
- Anchor companies + "Find similar companies" button → discovery flow returns 15 suggestions with one-line reasoning

**Second wow moment** at discovery results.

**Step 4 — First run, watched live.** No loading screen. Stream results in: "Searching Adzuna... 247 jobs... Filtering... 23 strong matches so far... 31..." Land on the Matches screen with first-run guidance overlay pointing at action shortcuts.

### Gift balance burn-down (replaces traditional "connect API key" step)

User never sees "API key" until they've gotten value. Cutover ladder:

| Threshold | Action |
|---|---|
| $5.00 used (50%) | Subtle dismissible notification: "When you have a few minutes, here's how to add your own key →" |
| $7.50 used (75%) | Persistent banner with inline "Set up now (30 seconds)" CTA |
| $9.00 used (90%) | Inline modal on next paid action. Two buttons: "Set up now" / "Continue with $1 left" |
| $10.00 used (100%) | Graceful degradation: read-only access preserved, paid actions disabled with tooltips. Banner: "Your data is safe. Add your key to resume." |

At $5 threshold, also show value summary: "23 jobs reviewed, 4 tailored resumes, 2 applications tracked." Anchor cost in value before asking for investment.

**BYO flow when triggered:** API key paste + monthly cap (default $5) + test button (free validation call). On success, switches all subsequent calls to user's key. Gift balance preserved as fallback if user's key fails.

### FTUE failure modes (designed-for, not deferred)

- **Resume extraction returned garbage:** confidence-flagged fields highlighted; paste-text fallback always available
- **Discovery found no companies:** auto-toggle remote-OK and re-run; if still empty, surface "expand search" controls
- **First run zero matches:** never show empty list; show partial-match jobs + one-click adjustment suggestions

---

## Post-onboarding search editing (settled)

**Edit affordance:** persistent search context bar above Matches list. `🔍 Engineering Manager • 25mi from 19103 • Remote OK • 6 anchor companies [Edit]`

**Two edit categories with different cost/UX profiles:**

**Tweaks** (filter-only, free): radius slider, remote-OK toggle, seniority filter, watchlist company add/remove. Re-filter existing scored pool client-side.

**Reframes** (semantic, paid): keyword changes, required-skills changes, major location shifts. Existing scores become stale.

**Live diff preview as user edits:**
```
Saving these changes will:
  • Add 47 jobs to your matches
  • Remove 12 jobs that no longer fit
  • Re-evaluate ~287 jobs (estimated cost: $0.09)
[ Save ]   [ Cancel ]
```

Critical for the gift-balance economy — prevents accidental $5 edits.

**Three save modes:**
- Pure expansion: free, next refresh pulls more jobs
- Pure narrowing: free, jobs filtered out of view but kept in DB
- Reframe: existing scores flagged "scored against old criteria," opt-in re-score button with cost

**Anchor companies edited separately** in a "Companies you're watching" sub-section. Different surface, different cost profile.

**Stale job auto-hiding:** jobs not seen in >30 days marked stale, hidden by default. Setting to adjust window.

---

## Distribution & signing (settled)

### macOS — do it right
- Code signing: "Developer ID Application" cert (free with Apple Developer Program). Drew has the program but only an "Apple Development" cert in keychain — needs to create the Developer ID cert at developer.apple.com.
- Notarization: required for clean Gatekeeper bypass on macOS 10.15+. Briefcase auto-notarizes when `notarytool` credentials are stored.
- Setup: ~1 hour first time, ~15 min per release.

### Windows — don't sign for v1
- Friends will see "Windows protected your PC" → "More info" → "Run anyway." Document this in the install guide with screenshots.
- EV code signing cert ($300-500/yr + hardware token) bypasses SmartScreen but is overkill for friend-favor scope.
- Mitigation for antivirus false positives on bundled Python: VirusTotal scan each release, link the clean report.

### Linux — don't bother
- AppImage GPG signing isn't enforced by anything mainstream
- Publish SHA256 checksum for paranoid users
- Linux users are technical enough to handle `chmod +x`

---

## Keyboard navigation (settled)

Dual-binding from day one: every action gets a button **and** a keyboard shortcut, with the shortcut visibly labeled (`Tailor (T)`).

| TUI | Web equivalent |
|---|---|
| `j/k` | `j/k` or `↑/↓` with row hover/focus |
| `Enter` | `Enter` or click row |
| `t` tailor | `T` + button "Tailor (T)" |
| `x` dismiss | `X` + button "Dismiss (X)" |
| `q` back | `Esc` (more web-native) |
| `/` search | `/` to focus filter box |

**New web-native additions:**
- URLs per match (`/matches/12345`) for bookmarkable/shareable jobs
- Native browser back/forward through Matches → Detail → Applications
- `?` overlay with shortcut help

Keyboard shortcuts on list-heavy screens only (Matches, Pipeline). Form-heavy screens use Tab+Enter only.

---

## Phased implementation plan

### Phase 0 — De-Drew-ify the core (estimated 1-2 days)

Strip jobTracker-isms, port the foundation into jobPilot's structure.

**Port:**
- `steps/filter.py` — Haiku match scoring with prompts and tool schemas. Parameterize for arbitrary user (not Drew's hardcoded EM config).
- `steps/tailor.py` — Sonnet resume customization. Pure port.
- `steps/dedup.py` — Cross-board duplicate merging. Pure port.
- `db.py` — Schema with `jobs`, `matches`, `runs`, `applications`, `status_history`, `company_gripes` tables. Drop `salary_notes`, replace with generic `notes` TEXT.
- `pipeline.py` — Step orchestration pattern. Strip launchd/SMTP triggers.
- `scrapers/greenhouse.py` + `scrapers/base.py` — Greenhouse scraper as reference scraper.

**Net new:**
- Bundled generic Typst resume template at `src/jobpilot/resources/templates/resume.typ` (replaces `~/.claude/plugins/` formatter dependency)
- Search params data model (per-user keywords/location/radius/remote/seniority) replacing hardcoded company list

### Phase 1 — Aggregator scrapers (estimated 2-3 days)

- `scrapers/adzuna.py` extending `BaseScraper`, returning `RawJob`. Search params = keywords + location + radius + seniority + remote.
- Geocoding via OpenStreetMap Nominatim (free, no key) for address → lat/lon
- Optional `scrapers/jsearch.py` for the paid upgrade tier (wired but disabled by default)

### Phase 2 — FastAPI web app + wizard (estimated 1 week)

- FastAPI app wrapping `src/steps/` orchestration
- Onboarding wizard (4 visible steps + welcome): resume upload → confirm extraction → search setup with discovery → first run
- Resume PDF/DOCX → YAML extractor (port `resume-skills:extracting-resumes` prompts to Anthropic SDK, not subprocess)
- Company discovery flow: Adzuna geo-query for companies in radius → Sonnet similarity ranking against anchor companies
- Matches list with status tracking, tailor button, keyboard shortcuts, search context bar
- Settings/edit-search modal with live diff preview
- BYO API key flow with cutover ladder
- Cost meter in app chrome
- Match-explanation sentence per filter result (small addition to filter prompt, large UX win)
- Interview prep button on job-detail screen + in-app HTML rendering (port `interview_prep.py` tool schema + prompt, parameterize role descriptor, Wikipedia summary fetch)

### Phase 3 — Multi-platform Briefcase distribution (estimated 2-3 days)

- Per-friend Anthropic workspace creation (~5 min/friend manual)
- Per-friend bundle build with embedded gift key
- macOS: Developer ID cert + notarization workflow
- Windows: AppImage + install-guide screenshots for SmartScreen
- Linux: AppImage build + SHA256 publishing

### Phase 4 — Cost guardrails & telemetry (estimated half day)

- Per-user monthly spend cap enforcement (pre-filter check)
- Token usage metering client-side, reconciled periodically with Anthropic billing API
- Pathological-search warning trigger
- Cost-per-action UI labels

---

## Open blockers / dependencies

- **Apple Developer ID cert.** Drew has Apple Developer Program but only "Apple Development" cert in keychain. Needs to create "Developer ID Application" cert at developer.apple.com before Phase 3 can ship a clean Mac build. Not blocking dev.
- **Anthropic workspace per-friend setup.** Manual ~5 min per friend in Anthropic console. Done at distribution time, not build time.
- **Adzuna API key.** Free signup; gate before Phase 1 testing.

---

## Deferred to v1.x

- Saved searches / multiple search profiles
- Behavioral edit suggestions ("you've dismissed 80% of director-level roles — drop the keyword?")
- In-app scheduler (background refresh while app is open)
- Gripes feature (Glassdoor/Reddit pain points)
- Interview prep PDF export (in-app HTML view ships in v1; Typst-rendered PDF download deferred)
- On-demand detailed Sonnet analysis per job
- Follow-up reminder UI (DB columns already there)
- `ghosted` status
- Search history / undo recent edits
- Edit-during-refresh queueing

## Deferred to v2

- Multi-resume support (different resumes per saved search)
- Cover letter generation
- Multi-tenant hosting
- User accounts / auth
- Billing
- Resume re-application history (`applications.job_id` PRIMARY KEY needs change)
- Cross-search dedup smarts

---

## Document conventions

- "v1" = first shipped version to friends
- "v1.x" = post-launch additions on the same architecture
- "v2" = warrants architectural rework or commercial-product framing
- "Drop" = no plans to add, ever, in this codebase
- "Defer" = explicit decision to add later, with reasoning preserved here
