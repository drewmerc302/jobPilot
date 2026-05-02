# jobPilot — 55-Issue Fix Roadmap

Generated 2026-05-01 from a deep code review. Each issue has:
- **Severity**: P0 critical / P1 important / P2 polish
- **Model**: recommended Claude tier for the work
- **Files**: primary surface to touch
- **Fix**: concrete what-to-do
- **Parallel group**: independent issues that can run in parallel without merge conflicts

---

## Severity legend
- **P0** — broken on shipped platform, data loss, or blocks user
- **P1** — wrong behavior, dead-end UX, misleading copy with cost impact
- **P2** — polish, naming, a11y, minor edge cases

## Model legend
- **opus** — multi-file architecture, cross-cutting refactor, security
- **sonnet** — feature-level edit, single bug across 1-3 files, copy + logic
- **haiku** — single-line change, rename, label/tooltip swap, CSS tweak

---

# Wave A — Foundational / Cross-platform (run FIRST, sequentially)

These touch packaging, paths, and global config. Other waves depend on them.

### A1 — Ship Typst binaries for all platforms `[P0, opus]`
- **Files**: `scripts/fetch_typst.sh`, add `scripts/fetch_typst.ps1`, add `scripts/fetch_typst.py`
- **Fix**: extend bash script to also download `typst-x86_64-apple-darwin.tar.xz` into `resources/typst/macos-x86_64/`. Update `_typst_binary()` in `src/jobpilot/steps/tailor.py:68` to detect `platform.machine()` and pick `macos-arm64` vs `macos-x86_64`. Create cross-platform Python launcher `scripts/fetch_typst.py` that handles all 4 archs. Document in README. Set Briefcase `universal_build = true` in `pyproject.toml:44` OR ship two builds.
- **Verify**: run on Intel Mac (or via `arch -x86_64`) → PDF generates.

### A2 — Sanitize `job['company']` in output paths `[P0, sonnet]`
- **Files**: `src/jobpilot/steps/tailor.py:284`, `src/jobpilot/routes/matches.py:368`
- **Fix**: add `_safe_dirname(s)` helper that strips/replaces `< > : " / \\ | ? *` and trims to 80 chars. Use for `job_dir`. Add unit test with `Marsh & McLennan`, `X / Twitter`, emoji.
- **Verify**: tailor a job with company name `Foo / Bar` on Windows.

### A3 — Auto-pick free port; retry on collision `[P1, sonnet]`
- **Files**: `src/jobpilot/app.py:36, 162-188`
- **Fix**: replace fixed `PORT = 8765` with `_pick_port(start=8765, attempts=20)` that probes via `connect_ex` and returns first free. If existing jobpilot is detected (probe `/health` endpoint — add one), open browser to it. Otherwise launch on new port. Persist last port to `~/.jobpilot/runtime.json`.
- **Verify**: run twice in parallel — both work or second opens to first.

### A4 — UTC date drift in `count_runs_today` `[P1, haiku]`
- **Files**: `src/jobpilot/db.py:589-593`
- **Fix**: replace `date(started_at) = date('now')` with `date(started_at, 'localtime') = date('now', 'localtime')`. Add migration note.
- **Verify**: daily cap resets at local midnight, not UTC.

### A5 — `pystray` Linux deps `[P1, haiku]`
- **Files**: `pyproject.toml:60-148`
- **Fix**: append `gir1.2-appindicator3-0.1` (debian) / `libappindicator-gtk3` (rhel) / `libappindicator-gtk3` (arch) to each `system_runtime_requires`.
- **Verify**: tray icon appears on Ubuntu 22.04.

### A6 — Lifespan auto-refresh races daily cap `[P1, sonnet]`
- **Files**: `src/jobpilot/app.py:78-99`
- **Fix**: check `db.count_runs_today() < config.max_runs_per_day` BEFORE starting auto-run. Mark auto-runs with a flag column (`runs.auto BOOL`) so manual cap counts manual only. Migration in `db._migrate`.
- **Verify**: cold-start auto-run doesn't decrement user-visible "3 of 4 left".

---

# Wave B — Independent UI/Logic (parallel, 8 buckets)

After Wave A merges. Each bucket is independent — assign to separate agents.

## Bucket B1 — Search-param classification + save flow `[sonnet]`

### B1.1 — Reframe classifier misses `remote_ok`, `seniority`, `radius_miles` `[P0]`
- **Files**: `src/jobpilot/routes/search_params.py:14, 32-40`
- **Fix**: extend `_classify` to compare `remote_ok`, `seniority`, `radius_miles`, and `anchor_companies` (set comparison). Any non-keyword/location change still re-filters but is cheaper than a full re-score — introduce 3rd category `"refilter"` with own preview copy "Existing matches re-filtered (free) and new scrapes will pull a wider net on next refresh."
- **Verify**: toggling Remote OK shows "refilter" preview, not "tweak".

### B1.2 — `search-params/save` always kicks pipeline `[P1]`
- **Files**: `src/jobpilot/routes/search_params.py:67-72`
- **Fix**: branch on classification. `tweak` / `refilter` → save and redirect to `/matches` with a toast. `reframe` → redirect to `/wizard/step/4` (kicks run). Add `?just_saved=1` for toast.
- **Verify**: tweak doesn't burn daily-cap slot.

## Bucket B2 — Run status / lifecycle `[sonnet]`

### B2.1 — `unknown` stage = dead poll `[P0]`
- **Files**: `src/jobpilot/routes/api.py:30-43`, `src/jobpilot/resources/templates/html/_partials/run_status.html:43-47`
- **Fix**: when stage is `"unknown"` or run row is missing, render an "error" partial with link `<a href="/wizard/step/4">Start a new search</a>`. No `hx-trigger`.
- **Verify**: visit `/wizard/step/4?run_id=999999` → see actionable message.

### B2.2 — Server restart leaves polling page hanging `[P1]`
- **Files**: `src/jobpilot/db.py:97-102`, `src/jobpilot/routes/api.py:30-80`
- **Fix**: when DB row has `error = 'App crashed'`, return error partial with that message. Surface in run_status template.
- **Verify**: kill app mid-run, restart, refresh wizard step 4 → see "Run interrupted, try again".

### B2.3 — `result.duration` undefined after restart `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/_partials/run_status.html:30`
- **Fix**: guard `{% if result and result.duration %}took {{ result.duration }}{% endif %}`.
- **Verify**: restart between completion and view — partial renders without orphan "took ".

## Bucket B3 — Dismiss / undo + status badge polish `[sonnet]`

### B3.1 — Add Undo for `dismiss_match` `[P0]`
- **Files**: `src/jobpilot/routes/matches.py:276-281`, `src/jobpilot/resources/static/app.js`, `src/jobpilot/resources/templates/html/_partials/match_row.html`
- **Fix**: dismiss handler returns empty + `HX-Trigger: matchDismissed` header carrying job_id, company, title. JS listener shows toast with "Undo" button → POST `/matches/{job_id}/undismiss` → on success, optionally reload row (or just redirect to /matches). Add route wrapping `db.undismiss_match`.
- **Verify**: dismiss row → toast → click Undo → row reappears on refresh.

### B3.2 — `withdrawn` badge same color as `new` `[P2]`
- **Files**: `src/jobpilot/resources/static/app.css:159`
- **Fix**: change `.badge-withdrawn` to `background:#f8f9fa;color:var(--gray);text-decoration:line-through;` or distinct hue.
- **Verify**: visual check.

### B3.3 — Status `<select>` lowercase options `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/_partials/status_badge.html:9`
- **Fix**: replace `{{ s }}` with `{{ s|capitalize }}` (Jinja filter) for display; keep `value="{{ s }}"` lowercase for storage.
- **Verify**: dropdown shows "New, Interested, Applied…".

## Bucket B4 — Banner / button polish `[haiku]`

### B4.1 — Disabled `↻ Refresh` is `<span>` `[P1]`
- **Files**: `src/jobpilot/resources/templates/html/matches.html:39`
- **Fix**: replace `<span class="btn btn-outline btn-sm" ...>↻ Refresh</span>` with `<button type="button" class="btn btn-outline btn-sm" disabled aria-disabled="true" title="Add your own key to refresh">↻ Refresh</button>`.

### B4.2 — Refresh-capped banner dismiss is ephemeral `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/matches.html:11`
- **Fix**: add `localStorage.setItem('dismissed_refresh_capped_'+todayDate,'1')`. Auto-hide on load same as `dismissed_ladder_50`. Add cleanup on date change.

### B4.3 — Two redundant buttons in over-budget alert `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/matches.html:18-23`
- **Fix**: collapse into single primary "Resolve →" button linking to `/settings#api_key`. Add anchor and scroll-into-view.

### B4.4 — `×` close buttons need `aria-label` `[P2]`
- **Files**: `matches.html:184`, `job_detail.html:197, 233`
- **Fix**: add `aria-label="Close"` to each close button.

## Bucket B5 — Settings + key management `[sonnet]`

### B5.1 — `Test key` can't test stored key `[P1]`
- **Files**: `src/jobpilot/routes/api.py:96-117`, `src/jobpilot/resources/templates/html/settings.html:42-51`
- **Fix**: if posted `api_key` is blank, fall through to `request.app.state.config.anthropic_api_key`. Update copy to "Test saved key" when field is empty.
- **Verify**: blank field + Test key → tests stored key.

### B5.2 — No way to clear API key `[P1]`
- **Files**: `src/jobpilot/routes/settings.py:35-58`, `settings.html`
- **Fix**: add separate `<form action="/settings/clear-key" method="post">` with confirm. Route nukes `anthropic_api_key`, `has_byo_key=False`, saves overrides. Surface "Clear key" only when key exists.
- **Verify**: clear key → ladder switches back to gift mode.

### B5.3 — `total_budget` (gift cap) not editable `[P2]`
- **Files**: `settings.html`, `src/jobpilot/routes/settings.py`, `src/jobpilot/config.py:37, 59-71`
- **Fix**: add advanced collapsible "Power user" section with `total_budget` slider $5–$50. Persist via `save_overrides`.

### B5.4 — Show client construct error early `[P2]`
- **Files**: `src/jobpilot/app.py:60`
- **Fix**: if `config.anthropic_api_key == ""` and not in gift mode, log warning and skip client init (set `app.state.client = None`). Routes already check ladder, but add a visible banner in base template when client is None and ladder=byo.

## Bucket B6 — Job-detail modals + tailor `[sonnet]`

### B6.1 — `open_tailor=1` script throws when modal absent `[P1]`
- **Files**: `src/jobpilot/resources/templates/html/job_detail.html:351-358`
- **Fix**: guard the script block with the same `{% if (has_analysis or has_full_description) and can_act %}` outer condition that gates the modal.
- **Verify**: navigate to `?open_tailor=1` on a job with no description → no console error.

### B6.2 — `apply_suggested_edits` over-replaces `[P1]`
- **Files**: `src/jobpilot/steps/tailor.py:91-123`
- **Fix**: switch from `if original in item: item.replace(original, suggested)` to exact equality first (`if item == original: items[j] = suggested`). Fall back to substring only when no exact match exists in the resume. Log when fallback fires.
- **Verify**: bullet that contains another bullet's text as substring is unaffected.

### B6.3 — Manual job add 400 loses form `[P1]`
- **Files**: `src/jobpilot/routes/matches.py:497-512`
- **Fix**: convert to HTMX response: re-render the modal with the error inline above the URL field and the user's typed values pre-filled. Add `add-job-result` slot in modal.
- **Verify**: submit with `javascript:alert(1)` → error appears, fields preserved.

### B6.4 — `_is_safe_url` doesn't catch `0.0.0.0` / `::` `[P1, security]`
- **Files**: `src/jobpilot/routes/matches.py:33-59`
- **Fix**: add `addr.is_unspecified` to the rejection list. Add IPv6 explicit check. Test cases for `0.0.0.0`, `::`, `::1`, `fe80::1`.

### B6.5 — `fetch_full_description` no max-length `[P2]`
- **Files**: `src/jobpilot/fetch_description.py:117-120`, `src/jobpilot/steps/tailor.py:127-171`
- **Fix**: cap returned text at 12_000 chars. Truncate `job_description` in `llm_resume_analysis` to 8_000 if longer.
- **Verify**: pasting a 200KB description doesn't blow up token bills.

## Bucket B7 — Profile + extraction `[sonnet]`

### B7.1 — Education silently wiped on save with no `edu_*` fields `[P0]`
- **Files**: `src/jobpilot/routes/profile.py:265`, `src/jobpilot/resources/templates/html/profile_edit.html:172-194`
- **Fix**: always render the Education card (drop `{% if profile.education %}` gate) with at least one empty row + "Add education" button. In `profile_save`, if zero `edu_*_institution` fields posted, preserve existing `profile["education"]` rather than overwrite to `[]`.
- **Verify**: save profile without touching education → existing education preserved.

### B7.2 — `Re-upload` discards extracted draft without warning `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/wizard.html:171`
- **Fix**: add `onclick="return confirm('Re-uploading will discard the extracted resume. Continue?')"`. Tooltip "Replace your resume — your edits to the extracted version will be lost."

### B7.3 — Extracted profile may lack required keys `[P2]`
- **Files**: `src/jobpilot/steps/extract_resume.py:204-219`
- **Fix**: defensively `.setdefault('experience', [])`, `'skills', {}`, `'education', []`, `'low_confidence_fields', []` on the returned profile.

## Bucket B8 — Copy + naming + a11y `[haiku]` (one agent, sequential mass-edit)

### B8.1 — Standardize "Target companies" everywhere `[P2]`
- **Files**: `wizard.html:223-227`, `matches.html:142`, `routes/wizard.py`, `routes/search_params.py`
- **Fix**: replace all "Anchor companies" labels with "Target companies". Keep the field name `anchor_companies` in form posts and the dataclass for now (rename later).

### B8.2 — Replace user-facing "tweak" / "reframe" with plain language `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/_partials/search_diff_preview.html`
- **Fix**: tweak → "Refines existing results" + "Free, no re-scoring". reframe → "Re-scores all matches" + cost. refilter (new) → "Re-filters existing matches".

### B8.3 — Rename `jobs_reviewed` → `jobs_scanned` `[P2]`
- **Files**: `src/jobpilot/db.py:595-612`, `src/jobpilot/resources/templates/html/_partials/key_ladder_banner.html:9`
- **Fix**: rename DB function key and template usage. Or change copy to "X listings scanned".

### B8.4 — Capitalization consistency `[P2]`
- **Files**: `job_detail.html:131-140`
- **Fix**: pick one — "Generate Tailored Resume" / "Re-generate Resume" (Title Case) OR sentence case for both.

### B8.5 — Unify "Full listing" labels `[P2]`
- **Files**: `job_detail.html:39, 179, 203, 312`
- **Fix**: standardize all on "Open original listing ↗".

### B8.6 — `data-tooltip` invisible on touch `[P1]`
- **Files**: `src/jobpilot/resources/static/app.css:223-272`, all templates using `data-tooltip`
- **Fix**: add `[data-tooltip]:focus::after, [data-tooltip]:active::after { opacity: 1 }` and make tooltip-bearing elements `tabindex="0"` if not already focusable. For column headers (non-interactive), convert to inline `(?)` icon with click-to-toggle.

### B8.7 — `Score` for manual jobs needs tooltip `[P2]`
- **Files**: `_partials/match_row.html:11-15`
- **Fix**: wrap the `—` in `<span data-tooltip="Manually added — click Analyze in job details to score.">—</span>`.

### B8.8 — "Why it fits" cell shows raw "Manually added" `[P2]`
- **Files**: `_partials/match_row.html:18`
- **Fix**: when `m.source == 'manual'` and `match_reason == 'Manually added'`, render `<span class="muted">Click Analyze for AI fit</span>`.

### B8.9 — "~$0.03 via Claude" → "~$0.03 in AI usage" `[P2]`
- **Files**: `job_detail.html` (multiple), `profile_edit.html:106`
- **Fix**: bulk find/replace.

### B8.10 — Tooltip on "+ Add your own job listing" `[P2]`
- **Fix**: replace with "Add a job from another site". Already has data-tooltip — just sharpen the visible label.

### B8.11 — `?` overlay focus trap `[P2]`
- **Files**: `src/jobpilot/resources/static/app.js:48-53`, `base.html:31-49`
- **Fix**: convert overlay to `<dialog>`. Use `showModal()` (gives focus trap for free). Update toggle key handler.

### B8.12 — `D` and `Enter` keyboard shortcuts overlap `[P2]`
- **Files**: `src/jobpilot/resources/static/app.js:35-42`, `base.html:39`
- **Fix**: drop the `d`/`D` handler. Update overlay table.

---

# Wave C — Cost / pricing / instrumentation `[sonnet]`

### C1 — Pricing table only knows two models `[P1]`
- **Files**: `src/jobpilot/pricing.py`
- **Fix**: add Opus pricing, add `claude-opus-4-7`, accept aliases without date suffix by stripping suffix. Log warning when model not in table.

### C2 — Greenhouse probe swallows all errors `[P2]`
- **Files**: `src/jobpilot/scrapers/greenhouse.py:36-52`
- **Fix**: distinguish 404 (board doesn't exist — silent OK) from 5xx/timeout (warn user). Surface "Greenhouse temporarily down — N target companies skipped" in run-status partial.

### C3 — Job-detail "Remote-friendly" warning false-negatives `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/job_detail.html:32`
- **Fix**: tighten regex — match `\bremote\b` only when preceded by "is", "fully", "100%", "hybrid", "open to" etc. Or just trust `job.remote` (drop the substring fallback) and add a dedicated "Remote unspecified" state.

### C4 — htmx vendor file no SRI / no version pin `[P2]`
- **Files**: `src/jobpilot/resources/templates/html/base.html:8`
- **Fix**: add `integrity="sha384-..."` and `crossorigin="anonymous"`. Document version in a comment.

---

# Parallelization map

```
Wave A (sequential, opus → sonnet → haiku):
  A1 → A2 → A3 → A4 → A5 → A6

Wave B (8 parallel agents after A merges):
  B1 [sonnet]   ─┐
  B2 [sonnet]   ─┤
  B3 [sonnet]   ─┤
  B4 [haiku]    ─┼──> all merge to main
  B5 [sonnet]   ─┤
  B6 [sonnet]   ─┤
  B7 [sonnet]   ─┤
  B8 [haiku]    ─┘

Wave C (after B merges, 1 sonnet agent):
  C1, C2, C3, C4
```

**Rationale for tier choices:**
- **opus** for A1 (cross-platform binary plumbing + Briefcase config + Python launcher — non-trivial).
- **sonnet** for most logic buckets (multi-file, real branching).
- **haiku** for B4 / B8 (mass copy/CSS edits, fast and cheap).

---

# Master checklist (55 items)

- [x] 1. A1 — Typst binaries: ship arm64+x86_64 mac, linux, windows
- [x] 2. A1 — `_typst_binary` arch detection
- [x] 3. A2 — sanitize `job['company']` for paths
- [x] 4. A3 — auto-pick free port + health probe
- [x] 5. A4 — UTC drift in `count_runs_today`
- [x] 6. A5 — pystray Linux deps in pyproject
- [x] 7. A6 — auto-refresh races daily cap
- [x] 8. B1.1 — reframe classifier handles remote_ok / seniority / radius
- [x] 9. B1.2 — search-params save: tweak doesn't kick pipeline
- [x] 10. B2.1 — unknown stage shows error + recovery link
- [x] 11. B2.2 — server-restart "App crashed" surfaces in UI
- [x] 12. B2.3 — guard `result.duration` in run_status partial
- [x] 13. B3.1 — undo dismiss with toast + route
- [x] 14. B3.2 — withdrawn badge distinct color
- [x] 15. B3.3 — capitalize status options for display
- [x] 16. B4.1 — disabled refresh = `<button disabled>` not `<span>`
- [x] 17. B4.2 — persist refresh-capped banner dismissal
- [x] 18. B4.3 — collapse two over-budget buttons to one
- [x] 19. B4.4 — `aria-label="Close"` on `×` buttons
- [x] 20. B5.1 — Test key tests stored key when field blank
- [x] 21. B5.2 — Clear key UI
- [x] 22. B5.3 — total_budget editable in advanced settings
- [x] 23. B5.4 — surface missing-key state in base template
- [ ] 24. B6.1 — guard `open_tailor=1` script
- [ ] 25. B6.2 — exact-match-first in apply_suggested_edits
- [ ] 26. B6.3 — manual-job-add error stays in modal
- [ ] 27. B6.4 — `_is_safe_url` catches 0.0.0.0 / IPv6 unspecified
- [ ] 28. B6.5 — cap fetched description length
- [ ] 29. B7.1 — Education preserved on profile save
- [ ] 30. B7.2 — Re-upload confirm dialog
- [ ] 31. B7.3 — extract_resume defensive defaults
- [ ] 32. B8.1 — "Target companies" everywhere
- [ ] 33. B8.2 — plain-language search-diff copy
- [ ] 34. B8.3 — `jobs_reviewed` → `jobs_scanned`
- [ ] 35. B8.4 — Generate/Re-generate caps consistent
- [ ] 36. B8.5 — unify "Open original listing"
- [ ] 37. B8.6 — tooltips work on touch devices
- [ ] 38. B8.7 — manual-job Score tooltip
- [ ] 39. B8.8 — manual-job "Why it fits" copy
- [ ] 40. B8.9 — "~$0.03 in AI usage"
- [ ] 41. B8.10 — "Add a job from another site"
- [ ] 42. B8.11 — `?` overlay focus trap (use `<dialog>`)
- [ ] 43. B8.12 — drop redundant `D` shortcut
- [ ] 44. C1 — pricing table extended + alias-strip
- [ ] 45. C2 — Greenhouse 404 vs 5xx distinguished
- [ ] 46. C3 — Remote-friendly warning logic
- [ ] 47. C4 — htmx SRI + version pin
- [x] 48. (rolled into A1) Briefcase universal_build / dual arch
- [x] 49. (rolled into A1) `fetch_typst.py` cross-platform launcher
- [ ] 50. (rolled into B7.3) low_confidence_fields default
- [ ] 51. (rolled into B6.4) IPv6 link-local in safe-url
- [x] 52. (rolled into B5.4) banner when client is None
- [x] 53. (rolled into B3.1) screen-reader announce on dismiss
- [x] 54. (rolled into B2.2) crashed-run UI message
- [x] 55. (rolled into B5.3) per-action cost projection in advanced settings

---

# Master prompt to run after clearing context

Paste this into a fresh Claude Code session in `/Users/drewmerc/workspace/jobPilot`:

```
You are tasked with executing a 55-issue fix roadmap on jobPilot. The roadmap
lives at docs/FIXES_ROADMAP.md — read it first.

Project context:
- Local-first FastAPI + htmx + SQLite job-search tool
- Source: src/jobpilot/
- Templates: src/jobpilot/resources/templates/html/
- Static: src/jobpilot/resources/static/
- Briefcase-packaged for macOS/Windows/Linux desktop
- Tests: tests/
- Run: `uv run python -m jobpilot` (opens http://127.0.0.1:8765)

Execution rules:
1. Wave A is sequential. Do A1 → A2 → A3 → A4 → A5 → A6 in order. After
   each item, run `uv run pytest tests/` and verify the local app boots.
   Commit after each item with subject `fix: <issue id> <short desc>` using
   /tmp/msg.txt + git commit -F.
2. Wave B may be parallelized via 8 cavecrew-builder subagents (see
   .claude config). Spawn one agent per bucket B1–B8 in a single message
   with multiple Agent tool blocks. Each agent's prompt should include the
   bucket's issues verbatim from FIXES_ROADMAP.md plus "commit each fix
   separately, run tests after each, do not touch files outside your bucket".
3. Wave C is one sonnet agent after B merges.
4. After every wave, run the full test suite and boot the app to smoke-test
   the wizard, /matches, and /settings pages.

Safety:
- Never push to remote without explicit approval.
- Never edit src/jobpilot/resources/typst/macos/typst (binary).
- Use the Edit tool for changes; Write only for new files.
- Resume code: never use heredocs for commit messages. Always
  Write /tmp/msg.txt then `git commit -F /tmp/msg.txt`.

Verification per issue:
- Each issue lists a "Verify" step. Run it. If it fails, do not mark complete.
- Update the checklist in docs/FIXES_ROADMAP.md by changing `[ ]` to `[x]`
  inline as each item lands.

Recommended model assignments (model is a hint — pick best for the bucket):
- A1: opus
- A2, A3, A6: sonnet
- A4, A5: haiku
- B1, B2, B3, B5, B6, B7: sonnet
- B4, B8: haiku
- C1, C2, C3, C4: sonnet

Start with A1 now. Read docs/FIXES_ROADMAP.md, confirm the section list,
then begin.
```
