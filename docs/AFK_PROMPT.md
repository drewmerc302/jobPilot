# AFK runner prompt — execute after `/clear`

Paste the block below verbatim into a fresh Claude Code session opened in
`/Users/drewmerc/workspace/jobPilot`. Tell Claude to run in **auto mode**
(`/auto`) before pasting if your harness needs it.

---

```
You are running an autonomous, end-to-end execution of the 55-issue fix
roadmap at docs/FIXES_ROADMAP.md while the user is AFK. Do not stop until
every checklist item is `[x]` and the final summary commit has landed on
the master branch locally. Do not push.

Project: /Users/drewmerc/workspace/jobPilot
Stack: FastAPI + htmx + SQLite, Briefcase-packaged, Python 3.13
Run: `uv run python -m jobpilot`
Tests: `uv run pytest tests/`
Lint: `uv run ruff check src/`

==============================================================
NON-NEGOTIABLES (these override anything else)
==============================================================
1. Read docs/FIXES_ROADMAP.md FIRST and use it as the source of truth.
2. Never push to a remote. Never run `git push`. Local commits only.
3. Never use bash heredocs for commit messages. Always:
     Write /tmp/msg.txt with the message
     git commit -F /tmp/msg.txt
4. Never use `git commit --amend`, `git reset --hard`, `git push --force`,
   `--no-verify`, or `rm -rf` on tracked files.
5. Never edit src/jobpilot/resources/typst/*/typst (binaries).
6. Never write secrets, API keys, or .env contents to commits.
7. Wave A is sequential. Do not start Wave B until A is fully merged
   AND tests pass.
8. After every commit, run tests. If tests fail, fix the failure in the
   same wave before moving on. If you cannot fix in 2 attempts, tag the
   issue `BLOCKED-<id>` in docs/FIXES_ROADMAP.md, commit a stub note,
   and continue with non-dependent work.
9. Use TaskCreate at the start to enumerate every issue from the
   roadmap as a task. TaskUpdate `in_progress` when starting each item,
   `completed` when its Verify step passes and the commit lands.
10. Do not ask the user clarifying questions — make reasonable
    assumptions, log them in the commit body, and continue.

==============================================================
WORKFLOW
==============================================================
Phase 0 — Setup (do once, sequentially):
  - Read docs/FIXES_ROADMAP.md end to end.
  - Run `git status`. If working tree is dirty, stash with
    `git stash push -u -m "afk-runner-pre-stash"`. Note the stash ref.
  - Create branch `git switch -c afk/fix-roadmap-$(date +%Y%m%d)`.
  - Run baseline `uv run pytest tests/ -x` and `uv run ruff check src/`
    to capture pre-existing failures. Record in /tmp/baseline.txt.
    Anything green at baseline must stay green.
  - TaskCreate one task per checklist item (47 numbered + the 8
    rolled-in sub-items). Set activeForm to the issue id (e.g. "B6.2").

Phase 1 — Wave A (sequential, in order A1 → A2 → A3 → A4 → A5 → A6):
  For each Wave A item:
    a. TaskUpdate in_progress.
    b. Apply fix per the roadmap. Use Edit for existing files,
       Write only for new files. Read before Edit.
    c. Run `uv run pytest tests/`. If new failures, fix.
    d. Run `uv run ruff check src/`. Fix any new findings.
    e. Smoke-boot: `uv run python -m jobpilot &` then `sleep 3`,
       `curl -fsS http://127.0.0.1:<port>/ -o /dev/null` (use whatever
       port the app picked — read from logs), then kill the process.
       Skip the boot test only if the change is purely string/CSS.
    f. Stage only the files you touched. Never `git add -A`.
    g. Write /tmp/msg.txt with subject `fix(<issue-id>): <short desc>`
       and a short body explaining the change + any assumption made.
       Commit with `git commit -F /tmp/msg.txt`.
    h. Edit docs/FIXES_ROADMAP.md to flip `[ ]` → `[x]` for that item.
       Commit that flip too (subject: `chore: mark <id> done`).
    i. TaskUpdate completed.

Phase 2 — Wave B (8 buckets B1..B8):
  Spawn 8 cavecrew-builder subagents in a SINGLE message with 8
  parallel Agent tool blocks. Each agent's prompt is:

    "You are executing bucket <Bx> from docs/FIXES_ROADMAP.md in the
     jobPilot repo at /Users/drewmerc/workspace/jobPilot. Do not touch
     files outside your bucket's listed paths. For each issue in your
     bucket: read roadmap, read affected files, apply fix, run
     `uv run pytest tests/`, run `uv run ruff check src/`, commit
     using /tmp/msg-<Bx>-<n>.txt + `git commit -F`. Subject format:
     `fix(<issue-id>): <desc>`. After each commit, edit
     docs/FIXES_ROADMAP.md to flip the matching `[ ]` to `[x]` and
     commit that flip. Do not push. Do not amend. If two issues touch
     the same file, do them sequentially. Return a one-line summary
     per issue at the end."

  After all 8 agents return:
    - `git log --oneline` to verify expected commit count.
    - Run full test suite. If any failure, debug — likely a cross-bucket
      interaction; fix in main thread.
    - Smoke-boot the app and click through wizard / matches / settings
      via curl GETs of: /, /wizard/step/0, /matches, /settings,
      /profile. Each must return 200 or expected redirect.

Phase 3 — Wave C (sequential, single sonnet pass):
  For C1, C2, C3, C4: same per-item flow as Wave A.

Phase 4 — Final verification:
  - Every checklist item in docs/FIXES_ROADMAP.md is `[x]`.
  - `uv run pytest tests/` passes.
  - `uv run ruff check src/` clean.
  - `uv run python -m jobpilot` boots, /matches and /settings return 200.
  - `git log --oneline master..HEAD | wc -l` matches expected commit count.
  - Write a final summary commit `docs: AFK roadmap complete` containing
    a status report at docs/AFK_RUN_REPORT.md with:
      * total issues fixed
      * any BLOCKED-<id> deferrals and why
      * test/lint/boot status
      * branch name
      * suggested next step for the user (e.g. "review and merge")

Stop conditions (in priority order):
  - All issues complete → Phase 4 → terminate with success summary.
  - Same test failure persists across 3 fix attempts on one issue →
    tag BLOCKED, commit stub, continue with non-dependent work.
  - Filesystem error / git error you cannot recover from → write
    /tmp/AFK_HALT.txt with full context, terminate.
  - Anthropic API auth error or rate-limit storm → wait 60s, retry
    once, then halt with /tmp/AFK_HALT.txt.

Begin now with Phase 0. Do not summarize the roadmap back to me — just
execute. Use TaskCreate, then start Wave A.
```

---

## Recovery if the run halts

If you return and find `/tmp/AFK_HALT.txt`, read it first — it explains
why. Otherwise, check:

```
cd /Users/drewmerc/workspace/jobPilot
git log --oneline master..HEAD
grep -c "^- \[x\]" docs/FIXES_ROADMAP.md   # done count
grep -c "^- \[ \]" docs/FIXES_ROADMAP.md   # remaining
```

To resume, paste the same prompt into a fresh session — it's
idempotent against the checklist.
