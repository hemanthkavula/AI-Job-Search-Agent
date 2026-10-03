# Production Hardening Review — 2026-10-03

This review treats the job-search agent as one production pipeline rather than a collection of independent scripts. The governing requirements are: broad U.S. Data Engineering discovery, employer/ATS authority for job details and posting dates, strict but non-destructive eligibility filtering, source-specific catch-up with no silent gaps, master-resume visual parity, JD-driven tailoring only when justified, persistent dashboard state, and reliable weekday cloud scheduling.

## Production invariants

1. **Open-ended source coverage** — configured employers are seeds, not an allowlist. Persisted employer/ATS enrichment expands production discovery over time.
2. **Employer authority** — aggregators are discovery leads only. The employer career page or ATS must be resolved before a job becomes application-ready.
3. **Posting-date authority** — board repost/refresh dates never override the employer/ATS posting date. Source-specific watermarks define catch-up windows.
4. **No silent source gaps** — a provider or Workday tenant advances its watermark only after the current scan succeeds. Old health records cannot advance a current watermark.
5. **U.S.-only targeting** — U.S.-scoped remote, hybrid and onsite jobs are allowed; explicit foreign locations are rejected.
6. **Data Engineering family** — Data Engineer plus legitimate adjacent IC Data Engineering titles are supported. Manager/Director/Architect/Consultant and unrelated families are rejected.
7. **Employment/work authorization** — Full-Time/W-2 focus; explicit no-future-sponsorship, citizenship-only and required-clearance postings are rejected. Unknown sponsorship is not rejected by assumption.
8. **Experience window** — configured minimum and maximum required-years bounds are inclusive.
9. **Prior-employer exclusions** — Fidelity Investments, Cigna/The Cigna Group and Target remain excluded from application eligibility.
10. **Resume decisioning** — verified but partial/low-target JDs use the unchanged master resume; sufficiently actionable JDs use JD-specific tailoring.
11. **Resume presentation** — the current master resume is the visual authority: two pages, Calibri, master color/spacing/alignment and 10/8/8 employer bullet counts.
12. **Application boundary** — automation ends at a validated, dashboard-published application package. Employer submission remains manual.
13. **Schedule** — production windows are Monday-Friday at 07:30, 10:00, 12:30, 15:30, 18:30 and 21:00 America/New_York, with redundant trigger/recovery protection.

## Defects found and corrected in this hardening pass

### Source-specific freshness was lost before finalization
Discovery already used provider-specific catch-up watermarks, but the cutoff was not persisted on individual jobs. Final employer-date verification could therefore compare a legitimate catch-up job against the newer global cutoff and reject it. Jobs now carry `freshness_cutoff`, so finalization uses the exact source interval that admitted the job.

### Historical source-health rows could affect current watermarks
`state/source_health.json` is cumulative. Previous code could treat an older successful tenant scan as if it happened in the current cycle. Current-cycle source/unit status is now built only from health rows whose `checked_at` belongs to the current discovery invocation.

### Workday diagnostic status objects were not normalized
Unit status can be a diagnostic object rather than a string. Scheduler watermark logic now normalizes both forms, allowing current `OK` Workday tenant scans to advance correctly.

### Learned providers and discovery portals were under-represented in scheduler status
The scheduler-facing status map now uses discovery's merged configured-unit coverage, so dynamically learned ATS sources and enabled discovery portals participate in provider watermark decisions.

### Quarantined sources could advance without being scanned
A known-unhealthy unit that was intentionally skipped is now classified as `DEGRADED`, not `OK`. Its watermark remains unchanged for later catch-up. The current slot can still close so recovery heartbeats do not repeatedly hammer a blocked source before its retry TTL.

### Partial providers could incorrectly close a slot
`PARTIAL` and `ERROR` now both leave the production slot open for a recovery heartbeat. Only a cycle without real provider failures is marked complete.

### Unit watermarks were being created for non-Workday providers
Unit-level watermarks are currently a Workday feature. Scheduler state now limits unit-watermark mutation to `workday:*` keys.

### U.S.-remote location false negatives and state-code false positives
Generic `Remote` jobs can now qualify when the JD explicitly establishes U.S. scope. State abbreviations are matched case-sensitively so ordinary words such as `in` and `or` cannot be misread as Indiana/Oregon. Explicit foreign location metadata remains a hard rejection.

### Experience maximum was exclusive by mistake
A configured range of 3–7 years previously rejected a job requiring exactly 7 years. The maximum is now inclusive.

### Employer enrichment was manual-only
Employer-universe enrichment now receives a weekday 05:30 ET scheduled run, using DST-safe UTC heartbeats plus a local-time guard. It runs ahead of the first 07:30 production slot and publishes its verified employer/source state for production restoration.

### Validation happened only after merge
Source Validation now runs for pull requests targeting `main` as well as pushes to `main`. Core production changes must pass the complete test suite before they are merged.

## Verification added

Regression tests cover U.S.-remote scope, foreign-location state-code collisions, the inclusive experience boundary, current-cycle source health, learned-provider status, source-specific freshness cutoffs, status-object normalization, partial-provider recovery behavior, degraded-source watermark retention and the DST-safe pre-production enrichment schedule.

## Production acceptance criteria

A production slot is healthy only when it can demonstrate all of the following:

- the requested ET slot was accepted exactly once;
- discovery restored and used provider/source-unit watermarks;
- current source coverage and provider failures are reported explicitly;
- failed or quarantined sources do not silently advance their watermark;
- fresh candidates are evaluated against the correct source-specific cutoff;
- board leads resolve to an authoritative employer/ATS destination before paid resume work;
- official employer posting age, live route and complete/usable JD are verified;
- final eligibility is re-evaluated from the resolved JD;
- the master-vs-tailored resume policy is followed;
- the master formatting contract and DOCX/PDF parity pass;
- only validated application packages reach `READY_TO_APPLY` and dashboard sync;
- previously applied history and resume references remain intact.

## Evidence status

Code-level regression tests and CI establish that the guarded behavior works for the modeled cases. They do not substitute for real-source production evidence. After this branch is merged and deployed, scheduled weekday cycles should continue to be inspected for source counts, failure reasons, watermark movement, finalization counts, resume outcomes and dashboard publication. Production evidence should be used to drive future changes instead of weakening eligibility or authority rules merely to increase counts.
