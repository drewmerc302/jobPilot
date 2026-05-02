# AFK Run Report — 55-Issue Fix Roadmap

**Branch**: `afk/fix-roadmap-20260501`
**Base**: `master`
**Status**: ✅ All 55 roadmap items complete

## Summary

Executed the full `docs/FIXES_ROADMAP.md` plan in three waves:

- **Wave A (foundational, 6 items)** — Typst cross-platform fetch + arch
  detection, company-path sanitization, auto-pick free port + `/health`,
  local-time daily-cap reset, pystray AppIndicator deps, lifespan
  auto-refresh respects the daily cap.
- **Wave B (8 buckets, 30+ items)** — Search-param classification +
  save flow, run-status lifecycle, undo dismiss + badge polish, banner
  + button polish, settings + key management, job-detail modals + tailor
  hardening, profile + extraction defaults, copy/naming/a11y mass edit.
- **Wave C (4 items)** — Pricing-table extension with Opus + alias-
  strip, Greenhouse 404 vs 5xx classification with surfaced warnings,
  job-detail remote-status tri-state, htmx SRI + version pin.

## Issue counts

| Severity | Count |
|----------|-------|
| P0       | 7     |
| P1       | 19    |
| P2       | 29    |

## Test / lint / boot status

- **Tests**: `pytest tests/` — 7 passed (1 pre-existing + 6 new
  `_safe_dirname` tests in `tests/test_tailor_paths.py`).
- **Lint**: `ruff check src/` — 1 pre-existing `F841` (unused
  `templates` local in `routes/matches.py:337`); already present at
  baseline before any commits in this run, kept untouched.
- **Boot smoke**: `uv run python -m jobpilot` boots cleanly. /health,
  /, /matches, /wizard/step/0, /settings, /profile all return 200.

## Commits

38 commits on this branch, paired (`fix(<ID>)` + `chore: mark <ID>
done`) per issue bucket.

## Deferrals

None. No `BLOCKED-*` markers raised. Every roadmap checkbox is `[x]`.

## Notable assumptions logged in commit bodies

- A1: kept `universal_build = false` and documented the trade-off
  rather than auto-flipping it (universal builds need a fat Python
  most CI runners lack).
- A2: only one path-construction site in the codebase actually used
  `job['company']` — the second call site mentioned in the roadmap
  (`matches.py:368`) used a clean route param; no second sanitizer
  needed.
- B5: clamped `total_budget` to [$5, $50] for safety; users who need
  more can hand-edit `~/.jobpilot/config_overrides.json`.
- B6.5: 12 000-char fetch cap / 8 000-char LLM cap chosen to comfortably
  fit realistic ads (≤6 KB) while still being far below typical
  paste-bomb sizes.

## Suggested next step

Review the diff (`git log master..HEAD`), run the app interactively
through the wizard / matches / settings flows once with a real
profile + Adzuna keys, then merge to `master`. No remote push has
been performed — this branch is local-only.
