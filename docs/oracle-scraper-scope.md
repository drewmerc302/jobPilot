# Scope: Oracle HCM Cloud scraper port

Port jobTracker's `OracleScraper` to jobPilot. Adds a major generic ATS
(Oracle Recruiting CE / `*.fa.oraclecloud.com`) used by JPMorganChase, Citi,
BofA, Disney, Amex, and many large employers jobPilot users will target.

Reference source: `~/workspace/jobTracker/src/scrapers/oracle.py` (jobTracker
commit `fe9311a`).

## What ports cleanly (copy + light adapt)

The REST flow is generic Oracle HCM — tenant-agnostic, works for any board:
- `recruitingCEJobRequisitions` listing endpoint (`finder=findReqs;...`)
- `recruitingCEJobRequisitionDetails` per-req detail endpoint
- `_parse_req`, `_compose_description`, `_extract_remote`, `_extract_salary`,
  `_build_url`, `is_job_live`
- tenacity retry decorator — identical pattern already in `scrapers/workday.py`

## What must change for jobPilot

1. **`RawJob` has no `source` field.** jobPilot stores source as a scraper
   *class attribute* (`source = "oracle"`), read by `steps/scrape.py:74`
   (`source=scraper.source`). jobTracker's `_parse_req` passes
   `source=self.source` into `RawJob(...)` — that arg does not exist on
   jobPilot's `RawJob` and will `TypeError`. **Drop it.** Keep the class attr.

2. **Hardcoded `keyword_search="engineering manager"`.** jobTracker is Drew's
   single-user EM search. jobPilot is generic/multi-user — the search term must
   come from the user's search params, OR fetch broad and let the existing
   `steps/filter.py` do matching (the approach `workday.py` already takes with
   `searchText=""`). Recommend: fetch with the user's primary role term (or
   empty) and filter downstream for consistency with Workday.

3. **Per-req detail fetch is expensive.** jobTracker fetches a detail page per
   relevant req (N extra requests + `request_delay` sleeps). jobPilot already
   has a lazy description fetcher (`fetch_description.py`; `workday.py` sets
   `description=None` and defers). Recommend the scraper return listing-level
   data only and defer descriptions to lazy fetch — cuts request volume sharply
   and avoids long synchronous scrapes blocking the pipeline.

## The hard part: tenant discovery

jobPilot's add-company flow is **dynamic probing** by company name, in parallel:
`routes/matches.py:161-170` and `:673-676`, plus `routes/wizard.py:419-421`,
fan out `probe_greenhouse` + `probe_lever` + `probe_workday` and pick the hit.
- greenhouse/lever probe by slug (`name → slug → try URL`)
- workday fans out instance/site combos (`probe_workday`)

**Oracle has no slug→tenant convention.** `{tenant}.fa.oraclecloud.com` — the
tenant is an opaque id (e.g. `ehzc`), and `siteNumber` (default `CX_1001`)
varies per employer. A name-based `probe_oracle` cannot reliably guess either.

**Decision: both A + B** (C rejected — blind probe too noisy on opaque tenants).
- **A: user pastes the Oracle careers URL.** Parse `tenant` + `siteNumber` from
  it during add-company. Reliable, ~zero false hits, unlimited coverage.
- **B: curated tenant map** for the top ~20 Oracle employers. Zero friction for
  the big names users actually target. Needs occasional upkeep (tenants drift).

**Resolution precedence** in `probe_oracle(company_name, url=None)`:
1. Company in curated map → use mapped `(tenant, siteNumber)`. Zero user effort.
2. Else `url` provided → parse `tenant` + `siteNumber` from it.
3. Else → return `None`. Oracle can't resolve this company; the other ATS
   probes still run, so add-company isn't blocked.

**Add-company UX:** add an optional "careers URL" field. Map covers the 80%
friction-free; the URL field is the catch-all for the tail. Surface a clear
error only when the user *expected* Oracle (pasted an oraclecloud URL) and it
failed to parse — not when Oracle simply wasn't the right ATS.

## Build sequence

1. `scrapers/oracle.py` — port + the 3 adaptations above. `source = "oracle"`,
   `tracks_full_company_listing = True`.
2. Tenant resolution per chosen option (A: URL parser; B: map).
3. `probe_oracle(company_name, url=None)` returning `OracleScraper | None`,
   mirroring `probe_workday`'s signature/`OracleProbeError` shape.
4. Wire into the 3 probe sites. **Note the stride:** current code indexes
   `probe_results[i*3 + k]` (matches.py:168-170). Adding a 4th probe means
   `i*4` and a 4th unpack at all sites — easy to miss one. Audit all three.
5. Register in `scrapers/__init__.py`.
6. Tests: fixture-based parse test (capture one real listing + detail JSON),
   following the `tests/test_scrapers.py` + `tests/fixtures/` pattern jobTracker
   used for Lever. Cover `_extract_remote` codes and `_extract_salary`.

## Effort

- Scraper port + adaptations: **~1-2 hrs** (mechanical).
- Tenant discovery (option A): **~1-2 hrs** (URL parse + add-company UI field).
- Probe wiring across 3 sites + stride fix: **~1 hr** (low-risk if audited).
- Fixtures + tests: **~1 hr**.
- **Total ~4-6 hrs**, dominated by the discovery UX, not the scraper.

## Failure modes to confirm in design

- Oracle returns full listing but empty descriptions → lazy fetch must handle
  per-req detail (decide where detail-fetch lives: scraper vs `fetch_description`).
- `siteNumber` wrong (default `CX_1001` mismatched) → listing endpoint 404s;
  surface as a clear add-company error, not a silent zero-result.
- Rate limiting on large boards (JPMC has thousands of reqs) → `max_pages` /
  `request_delay` caps; log when truncated rather than silently capping.
- Probe stride bug: forgetting one `i*3 → i*4` site corrupts result mapping for
  *all* ATSes, not just Oracle. Test the probe fan-out explicitly.

## Status — SHIPPED (2026-06-16)

Tenant discovery: **both A + B** (map first, URL fallback). Implemented:
- `scrapers/oracle.py`: `OracleScraper` + `probe_oracle(name, *, keywords, url)`
  + `_parse_oracle_url` + curated `_TENANT_MAP` (seeded with JPMorganChase =
  `jpmc`/`CX_1001`, verified from jobTracker config).
- `SearchParams.oracle_overrides` + `SearchParamsStore.add_oracle_override` so a
  URL-resolved company survives future refreshes (otherwise the name-only
  refresh path would silently drop it).
- Wired into all 3 probe sites (`routes/matches.py` ×2, `routes/wizard.py`),
  stride `i*3 → i*4` on the two anchor-loop sites.
- Add-company modal: optional careers-URL field; the URL is persisted on success.
- `tests/test_oracle.py` (13 cases): URL parse, probe precedence, req parse,
  remote codes, title prefilter, overrides round-trip + legacy-JSON back-compat.

### v1 behaviors / deviations to note
- **Detail fetch stays in the scraper** (not deferred to `fetch_description`):
  the public Oracle job page is a JS SPA, so the lazy URL fetcher can't recover
  descriptions — the REST detail endpoint is required.
- **Title keyword prefilter before detail fetch.** Unlike Greenhouse/Workday
  (which return everything and let `filter.py` decide), Oracle prefilters by the
  user's `keywords` to bound the per-req detail fetch, plus a `max_details=200`
  hard cap (logged when hit). Empty keywords → no prefilter, cap still applies.
  Tradeoff: a relevant job whose title lacks a keyword substring can be missed.
- **Anchor-refresh resolves via map + stored override only** (no live URL at
  refresh time, by design — the URL is captured once at add-company).

### Not done (future)
- Expand `_TENANT_MAP` with more verified employers (Citi, BofA, Disney, …) —
  needs each tenant confirmed against the live board before adding.
- `siteNumber` mismatch currently yields zero results, not a distinct error.
