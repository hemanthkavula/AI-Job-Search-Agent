# AI Job Search Agent

A production-oriented U.S. Data Engineering job-search system that discovers jobs, applies strict eligibility rules, resolves authoritative employer postings, generates or reuses resumes according to JD quality, validates artifacts, builds a manual application queue, and syncs the queue to a persistent hosted dashboard.

## Current production flow

```text
05:30 ET employer/source enrichment
→ scheduled production trigger
→ broad configured + learned multi-source discovery
→ source-specific freshness + canonical deduplication
→ U.S.-only / Data-Engineering-family eligibility
→ Full-Time / W-2 eligibility
→ experience + sponsorship + citizenship + clearance checks
→ authoritative employer/ATS resolution
→ official employer posting-date + live-route verification
→ complete/usable original JD retrieval
→ final eligibility on resolved JD
→ master-resume fallback OR JD-specific tailoring
→ ATS + evidence + recruiter + human-quality validation
→ targeted retry when a validation gate fails
→ master-format DOCX + PDF parity validation
→ READY_TO_APPLY
→ persistent application queue
→ hosted dashboard sync
→ user manually opens employer application and submits
→ user marks application Applied
→ applied status + resume reference remain persistent
```

Application submission is intentionally manual. The production agent prepares qualified applications and resumes but does not autonomously submit employer applications.

## Production schedule and reliability

Production runs Monday-Friday in **America/New_York** at six requested slots:

**07:30, 10:00, 12:30, 15:30, 18:30, and 21:00 Eastern.**

Cloudflare can dispatch the production workflow during each slot's recovery window, and GitHub Actions provides an independent DST-safe scheduled fallback. The Python scheduler applies the final America/New_York slot guard and `last_completed_slot` protection, so redundant heartbeats are safe no-ops after a completed slot.

Each provider resumes from its own watermark. Workday tenants additionally maintain independent unit watermarks. A provider that returns `ERROR` or `PARTIAL` keeps the slot open for recovery and retains its previous watermark. A known-unhealthy quarantined source is reported as `DEGRADED`; its watermark is retained for later catch-up without repeatedly hammering the same blocked endpoint during the current slot.

The reliability model is therefore:

```text
Cloudflare heartbeat + GitHub scheduled fallback
→ America/New_York slot guard
→ duplicate-completion protection
→ provider/unit watermark catch-up
→ recovery heartbeat for real partial failures
```

## Eligibility policy

The production pipeline targets appropriate individual-contributor Data Engineering roles, including Data Engineer, Senior/Staff/Principal Data Engineer, Analytics Engineer when the JD is truly Data Engineering, Data Platform Engineer, Data Infrastructure Engineer, Data Pipeline Engineer, Data Warehouse Engineer, ETL Engineer, Big Data Engineer, and related cloud-focused Data Engineering roles.

Hard filtering includes:

- United States roles only. Onsite, hybrid, and U.S.-scoped remote roles are allowed.
- Generic `Remote` requires U.S. evidence from the posting unless the discovery source itself is explicitly U.S.-scoped.
- Data Engineering role family only.
- Full-Time / W-2 focus.
- Configured experience bounds are inclusive.
- Reject when the posting explicitly says current or future employment sponsorship is unavailable.
- Reject explicit U.S.-citizenship requirements.
- Reject roles requiring a security/public-trust clearance.
- Reject non-IC Manager, Director, Architect, and Consultant role families even when Data Engineering terminology appears in the title.
- Unknown sponsorship status is not automatically rejected.

## Discovery and employer universe

Discovery is employer/ATS-first and open-ended rather than an allowlist.

- The static source catalog is seed coverage, not the complete employer universe.
- A weekday **05:30 ET** enrichment workflow expands the employer universe before the first 07:30 production slot using public/authoritative company feeds, evidence-backed domain resolution, career-page discovery, and ATS-tenant resolution.
- Production discovery merges configured seeds with persisted learned sources before collecting current jobs.
- Direct employer career pages and ATS boards are primary.
- Dice, ZipRecruiter, Wellfound, Built In, YC Jobs and other enabled public adapters are supplemental discovery only.
- LinkedIn Jobs, Indeed and Glassdoor remain disabled unless an authorized integration is available. Access controls are never bypassed.
- Aggregator discoveries must resolve to an authoritative employer/ATS posting before paid resume work or application readiness.
- The employer/ATS posting date is authoritative. Aggregator repost/refresh timestamps never override it.
- Unknown employers are allowed; target-company lists are priorities/examples, never hard allowlists.
- Fidelity Investments, Cigna Healthcare/The Cigna Group, and Target Corporation are explicit prior-employer exclusions.

Discovery state is persisted across cloud runs. Provider-specific cutoffs are carried with each discovered job through final employer-date verification so catch-up jobs are not incorrectly rejected by a newer global window.

## Resume decisioning and tailoring

The current master resume is the fixed visual and factual anchor. Its identity, chronology, education and employer history remain fixed, and its visual contract is preserved in every released resume.

The current master visual contract includes:

- two-page layout
- Calibri typography
- accent color `1F4E79`
- master margins, spacing, section structure and right-aligned dates
- selective phrase bolding
- exactly 10 Fidelity bullets, 8 Cigna bullets and 8 Target bullets
- Environment lines and the existing education structure

Resume content decisioning follows the verified JD:

1. Resolve and verify the employer/ATS JD and application route.
2. Build the safe JD coverage target set.
3. If the JD is partial/short or yields only **0–2** safe tailoring targets, use the master/profile resume unchanged.
4. If the JD is usable and yields **3 or more** meaningful targets, generate a JD-specific resume.
5. Tailored Summary, Technical Skills and experience wording can reflect the JD while preserving employer/domain coherence and fixed candidate facts.
6. Never invent employers, titles, dates, locations, education, certifications, unsupported numerical achievements or named business outcomes.

The complete verified JD is the technical-content source for tailoring; the master resume is not a technical-keyword whitelist.

## Resume validation

JD-tailored resumes pass automated quality gates before they can enter the application queue. Validation covers material JD coverage, ATS-oriented structure, experience depth, evidence consistency, recruiter readability, human-quality checks, repetition/metric controls and the master visual-format contract.

Failed tailored resumes are retried against the specific failed gates, up to the configured maximum. Master fallback resumes do not spend an LLM generation call.

Only an approved DOCX is promoted to the final resume tree. The corresponding PDF is generated from that same DOCX and must pass artifact/parity validation. A job reaches `READY_TO_APPLY` only after all required gates pass.

There is no artificial production resume-count cap: all jobs that qualify in a production cycle can proceed, subject to normal runtime/API constraints.

## Hosted application dashboard

The persistent hosted dashboard is the user-facing application queue and run-history surface.

For each queued application it can show the role/company, application status, source/portal, pipeline/run context, validated resume PDF, employer application link, and applied date/status. Per-row actions operate on one application rather than globally deleting history.

The user opens the employer application, completes submission manually, then selects **Mark Applied**. Applied status is persisted independently of subsequent production syncs. The associated resume reference is preserved, with recovery support for older applied records whose current ledger entry no longer contains the PDF path.

## Automation boundary

The automated production boundary is:

```text
Enrich sources
→ discover
→ qualify
→ resolve employer posting
→ verify posting date/live JD
→ choose master or tailored resume
→ validate resume + artifacts
→ queue
→ sync dashboard
```

The final employer submission remains a user action. The system does not run autonomous browser submission agents.

## State and cloud operation

Scheduled production runs in GitHub Actions. Generated scheduler state, provider/unit watermarks, discovery state, employer/source registries, ledger data, resume artifacts and queue data are carried across runs and synchronized to the hosted dashboard. The dashboard stores persistent application state on its attached volume.

The user's laptop does not need to remain on for scheduled enrichment, discovery, resume generation, artifact validation, queue creation, dashboard synchronization or scheduler recovery.

## Release and validation policy

Source Validation runs on pull requests targeting `main` and again on pushes to `main`. Production behavior changes should not be merged until the full repository test suite passes.

Automated tests establish code-level behavior; they do not replace real-source operational evidence. Scheduled production cycles should continue to be inspected for source coverage, provider failures, watermark movement, eligibility reasons, finalization counts, resume outcomes and dashboard publication.

## Safety and accuracy

The system must not fabricate fixed candidate facts, employers, chronology, education, certifications, numerical achievements, or screening-question answers. Eligibility decisions preserve explicit evidence from the posting. Failed or quarantined source scans retain their previous watermark so temporary provider problems do not silently create discovery gaps.

See **[docs/IMPLEMENTATION_REVIEW_2026-10-03.md](docs/IMPLEMENTATION_REVIEW_2026-10-03.md)** for the current hardening review and **[PROJECT_STATUS.md](PROJECT_STATUS.md)** for implementation history.
