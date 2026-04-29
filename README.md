# jobPilot

LLM-assisted job tracker, distributed as a double-clickable native app for macOS, Windows, and Linux.

## Status: packaging spike

Currently a Briefcase-based proof of concept verifying that:

- A FastAPI server can run inside a bundled `.app`
- A non-Python binary (Typst) can be vendored into the bundle and invoked at runtime
- The full pipeline produces a signed `.dmg` for macOS distribution

The actual jobTracker functionality (scrapers, LLM filter, resume tailoring, etc.) is **not yet ported** from `~/workspace/jobTracker/`. See `project_shareable_redesign.md` memory for the phased plan.

## Building locally (macOS)

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Briefcase (`uv tool install briefcase`).

```bash
# Fetch the bundled Typst binaries (one-time, ~120 MB across all platforms)
./scripts/fetch_typst.sh

# Generate the .app bundle layout
briefcase create macOS

# Compile the bundle
briefcase build macOS

# Run it (server on http://127.0.0.1:8765, browser opens automatically)
briefcase run macOS

# Produce a distributable .dmg
briefcase package macOS --adhoc-sign           # for local testing
briefcase package macOS --identity "Developer ID Application: ..."  # for distribution
```

## Code signing

For distribution to other Macs, the `.app` must be signed with a **Developer ID Application** certificate (not "Apple Development", which is dev-only). Create one at <https://developer.apple.com/account/resources/certificates/list>.
