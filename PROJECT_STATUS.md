# AI Job Search Agent — Current Production Status

**Target:** U.S. Data Engineering roles  
**Mode:** cloud production pipeline through `READY_TO_APPLY`; employer submission is manual  
**Timezone:** `America/New_York`  
**Production slots:** Monday-Friday at **07:30, 10:00, 12:30, 15:30, 18:30 and 21:00 ET**

This file describes the current production contract. Historical implementation notes that conflict with this file, the current README, or the candidate profile are not authoritative.

## 1. Product objective

Discover newly posted U.S. Data Engineering jobs across a broad employer/ATS universe, preserve missed intervals through source-specific watermarks, verify the employer's authoritative posting/JD/application route, enforce candidate eligibility, produce the correct master or JD-specific resume, validate the released DOCX/PDF, and publish qualified applications to the persistent hosted dashboard.

The automation boundary is deliberately:

```text
employer/source enrichment
→ discovery
→ freshness + deduplication
→ preliminary eligibility
→ employer/ATS resolution
→ official posting-date + live-route verification
→ complete/usable JD verification
→ final eligibility
→ master-resume fallback OR JD-specific tailoring
→ resume/content/artifact validation
→ READY_TO_APPLY
→ dashboard sync
```

Employer application submission remains a user action.

## 2. Scheduling and recovery

Production runs at these six ET slots:

- 07:30
- 10:00
- 12:30
- 15:30
- 18:30
- 21:00

Cloudflare may dispatch the GitHub production workflow during each 55-minute recovery window. GitHub Actions also has an independent DST-safe scheduled fallback. The Python scheduler is the final authority: it converts to `America/New_York`, accepts only the six configured slots, and uses `last_completed_slot` to make redundant heartbeats safe.

Recovery state is source-aware:

- each provider has its own watermark;
- Workday tenants additionally have independent unit watermarks;
- `OK` advances the relevant watermark;
- `PARTIAL` and `ERROR` retain the prior watermark and keep the current slot retryable;
- `DEGRADED` means a known-unhealthy unit was intentionally quarantined, so its watermark is retained for later catch-up without repeatedly hammering it during the same slot;
- a five-minute overlap is added around source windows to reduce boundary misses.

## 3. Employer-universe enrichment

A separate weekday enrichment workflow is scheduled for **05:30 ET**, before the first 07:30 production slot. It uses DST-safe UTC schedule entries plus a local-time guard.

Enrichment is open-ended, not a target-company allowlist. It combines configured sources with public/authoritative employer feeds and persistent learning, then attempts to resolve:

- employer identity;
- evidence-backed official domain;
- employer career page;
- hosted/embedded ATS family;
- executable ATS tenant/identifier.

Resolved sources are persisted and merged into later production discovery. Static companies are seeds, examples, or priorities—not a hard employer restriction.

## 4. Discovery source policy

Direct employer career pages and ATS boards are primary. The source registry supports a broad ATS family set and dynamically learned sources.

Supplemental public boards can be used for discovery when an executable adapter is available, including currently configured Dice, ZipRecruiter, Wellfound, Built In and YC Jobs. A board hit is never sufficient by itself for application readiness.

LinkedIn Jobs, Indeed and Glassdoor remain disabled unless an authorized integration is available. Access controls are not bypassed.

Every aggregator-origin job must resolve to an authoritative employer/ATS destination before paid resume work. The employer/ATS posting date—not a board repost/refresh timestamp—is the freshness authority.

## 5. Freshness and no-gap contract

Freshness is strict:

- explicit posting/publication fields are preferred;
- generic `updated_at` can be provisional discovery evidence only when no real posting field exists;
- aggregator dates are discovery evidence only;
- finalization re-reads authoritative employer/ATS posting evidence when required;
- source-specific catch-up cutoffs are attached to jobs and preserved through finalization;
- a source that did not actually complete the current scan must not advance because of an older source-health record.

This is intended to prevent both stale-job false positives and silent loss of jobs after provider outages.

## 6. Target job family

The pipeline accepts appropriate individual-contributor Data Engineering roles, including:

- Data Engineer
- Senior / Sr Data Engineer
- Staff Data Engineer
- Principal Data Engineer
- AWS / Azure / Cloud Data Engineer
- Big Data Engineer
- Data Platform Engineer when the work is genuinely Data Engineering
- Data Infrastructure Engineer
- Data Pipeline Engineer
- Data Warehouse Engineer
- ETL Engineer
- Analytics Engineer when the JD contains strong Data Engineering evidence

Manager, Director, Architect and Consultant role families remain hard exclusions. Unrelated analyst, scientist, frontend, QA, generic software-only, ML, DevOps/SRE, DBA, BI-only, internship and junior roles remain outside scope.

## 7. Location, employment and eligibility

Location policy:

- U.S. only;
- U.S. onsite, hybrid and U.S.-scoped remote are allowed;
- generic `Remote` must establish U.S. scope from reliable posting evidence unless the discovery source is explicitly U.S.-scoped;
- explicit foreign location metadata is rejected;
- U.S. state abbreviations are matched case-sensitively to avoid treating normal words such as `in` or `or` as state codes.

Employment policy:

- Full-Time / W-2 focus;
- reject explicit C2C, 1099, part-time, internship, temporary, seasonal and incompatible contract arrangements.

Experience policy:

- current candidate target is approximately 5+ years;
- configured required-experience window is inclusive at both minimum and maximum bounds.

Work-authorization screening:

- explicit current/future sponsorship unavailable → reject;
- explicit U.S.-citizenship-only requirement → reject;
- required security/public-trust clearance → reject;
- sponsorship available → continue;
- sponsorship not stated → continue rather than assuming rejection.

Prior-employer exclusions remain:

- Fidelity Investments
- Cigna Healthcare / The Cigna Group
- Target Corporation

## 8. JD authority and finalization

Preliminary eligibility is intentionally lightweight. Before resume generation, finalization must resolve and verify the authoritative employer/ATS job.

Final checks include:

- non-aggregator application destination;
- employer/ATS posting age within the correct source-specific cutoff;
- live application page/requisition;
- complete or safely usable JD;
- final eligibility re-run on the resolved JD;
- supported application route.

A dead, stale, unresolved or unverifiable posting is held/rejected before paid resume generation.

## 9. Resume decisioning contract

The current master resume is both the factual anchor and visual template.

Fixed identity/chronology includes:

### Fidelity Investments — Senior Data Engineer — Jan 2025–Present
- Jersey City, NJ
- finance/trading/risk/compliance context
- **10 bullets**

### Cigna Healthcare — Data Engineer — Jan 2022–Dec 2023
- Bangalore, India
- healthcare/claims/eligibility/EHR/HIPAA context
- **8 bullets**

### Target Corporation — Data Engineer — Jan 2020–Dec 2021
- Bangalore, India
- retail/POS/sales/inventory/merchandising context
- **8 bullets**

Education remains MS Computer Science, Rowan University, Glassboro, NJ, Jan 2024–Dec 2025.

Decision rule:

1. verify the JD;
2. build the safe coverage target set;
3. partial/short JD or only **0–2 safe tailoring targets** → use the master/profile resume unchanged;
4. usable JD with **3+ meaningful targets** → generate a JD-specific resume;
5. preserve fixed identity, chronology, education and domain coherence;
6. never invent employers, dates, titles, certifications, education, unsupported metrics, named projects or unsupported outcomes.

The JD is the technical tailoring source. The master resume is not a keyword whitelist.

## 10. Master visual contract

All released resumes follow the current master formatting contract:

- two pages;
- Calibri;
- accent `1F4E79`;
- current master margins/spacing/dividers;
- header/contact structure;
- two summary paragraphs;
- Technical Skills category formatting;
- employer/location/date alignment;
- Roles & Responsibilities label;
- selective bold emphasis;
- Environment lines;
- exact 10/8/8 experience bullet counts;
- education structure and pagination.

The formatter has a strict master-format validation gate for the production candidate profile.

## 11. Resume quality and artifact release

Tailored resumes are generated as temporary drafts and audited before promotion. Quality checks include:

- material JD coverage;
- internal ATS-oriented heuristic checks;
- experience-depth/evidence checks;
- recruiter/readability/human-quality checks;
- repetition and metric controls;
- fixed-fact consistency;
- master structural/visual rules.

Targeted regeneration is capped at three attempts. Passed coverage is carried forward when correcting later audit failures.

Only an approved DOCX is promoted to the final resume directory. The PDF is generated from that same approved DOCX and must pass parity/artifact validation. A rendering failure holds the unchanged approved DOCX; it does not spend another LLM call or silently release a different document.

`READY_TO_APPLY` requires the required content and artifact gates to pass.

## 12. Dashboard and application history

The Railway-hosted dashboard is the persistent user-facing queue/run-history surface. It supports application rows with role/company, source, pipeline/run context, validated resume, application link and applied date/status.

Per-row delete must affect only that application. Applied confirmations are persisted separately from ordinary production sync state. Associated resume references are preserved/recoverable for historical applied rows.

The dashboard stores persistent state on its attached Railway volume.

## 13. Persistent state

Production state includes:

- canonical job/requisition identity;
- source IDs and URLs;
- first/last seen information;
- eligibility and rejection reasons;
- authoritative JD/application route state;
- source-specific freshness cutoff;
- provider watermarks;
- Workday unit watermarks;
- current source health + retry/quarantine state;
- resume paths and audits;
- queue/application state;
- applied confirmations;
- employer/source registries.

## 14. CI and release policy

Source Validation runs on pull requests targeting `main` and again after pushes to `main`. It validates source configuration and executes the full repository test suite.

Production behavior changes should be merged only after pre-merge validation passes. After merge, Railway deployments and the next scheduled production cycles should be checked separately; green unit/regression tests are not a substitute for real-source production evidence.

## 15. Operational success criteria

A healthy weekday production slot should:

1. be accepted exactly once for the intended ET slot despite redundant triggers;
2. restore employer/source and scheduler state;
3. discover from configured + learned executable sources;
4. report current provider/unit coverage and failures;
5. retain watermarks for failed/quarantined sources;
6. apply source-specific freshness without losing catch-up jobs;
7. deduplicate cross-source/historical copies;
8. reject non-U.S./wrong-family/incompatible-employment/experience/sponsorship/citizenship/clearance jobs;
9. canonicalize board leads to authoritative employer/ATS postings;
10. verify official posting age, live route and JD quality;
11. choose master fallback vs JD-tailored resume correctly;
12. preserve the master visual contract;
13. release only parity-validated DOCX/PDF artifacts;
14. publish only valid application packages to the dashboard;
15. preserve prior applied history and resume references.

## 16. Evidence status and next operations

The repository has extensive automated tests and prior successful cloud runs, but source behavior changes continuously. The current hardening work must therefore be followed by real scheduled-run inspection rather than assumptions.

Continue monitoring:

- employers/ATS units attempted;
- provider-family coverage;
- discovery counts by source;
- stale/missing-date rejections;
- source failure and quarantine reasons;
- watermark movement;
- preliminary vs final eligibility;
- resume master-vs-tailored decisions;
- audit/artifact outcomes;
- dashboard queue sync;
- applied-history persistence.

No implementation can guarantee every job on the public internet: private/internal openings, blocked sites, partner-only feeds and jobs not publicly exposed remain outside guaranteed coverage. The production goal is broad, evidence-backed, continuously expanding coverage without weakening authority, freshness or eligibility rules.

See `docs/IMPLEMENTATION_REVIEW_2026-10-03.md` for the latest hardening findings and regression coverage.
