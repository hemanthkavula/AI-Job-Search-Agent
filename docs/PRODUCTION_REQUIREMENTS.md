# AI Job Search Agent — Production Contract

This document is the canonical behavior expected from production cycles. It is intentionally written as testable invariants rather than a target-company allowlist.

## 1. Discovery scope

- United States jobs only. Remote, hybrid, and onsite are all eligible when the role is US-based.
- Target-company lists are discovery seeds/examples only. A job must never be rejected merely because its employer is not in a configured target-company list.
- Discover broadly from employer ATS tenants, employer-owned career pages, and US job boards/portals.
- Board results are leads. Resolve the employer/ATS posting and prefer the employer application URL. Keep Easy Apply only when the posting is reliable, sufficiently complete, and no stronger employer route is available.
- Discovery is incremental. Every source unit/tenant owns its own successful watermark. A later cycle starts after that source unit's previous successful watermark. Failed/interrupted units do not advance their watermark and therefore catch up on the next cycle.
- Employer-universe enrichment is asynchronous and must not block the production cycle.

## 2. Data-engineering family

A posting is eligible only when semantic analysis shows that the work belongs to the data-engineering family. Do not rely on an exact title string. Signals include data pipelines, ETL/ELT, data platforms, analytics engineering, data modeling, warehouses/lakehouses, distributed/streaming processing, Spark, Kafka, Databricks, Snowflake, dbt, Airflow, cloud data services, SQL/Python and related DE technologies.

Use deterministic rules for obvious cases and the job-analysis LLM for ambiguous titles/JDs. The LLM may expand recall; it must not override hard eligibility constraints below.

## 3. Hard eligibility constraints

Evaluate the complete authoritative job description whenever available.

- Experience: accept requirements from 3 years through less than 7 years. Reject explicit requirements below 3 years. Reject any minimum requirement of 7+ years (including equivalent wording such as seven years, 8–10 years, decade of experience, etc.). Preferred/non-required experience should not be treated as a hard minimum unless the wording makes it a requirement.
- Sponsorship: reject explicit statements that employment/visa sponsorship is unavailable now or in the future, including semantically equivalent wording. If sponsorship is not mentioned, continue. If sponsorship is explicitly available, continue.
- Citizenship: reject jobs requiring US citizenship or equivalent citizenship-only eligibility. Do not reject ordinary work-authorization questions that do not require citizenship.
- Clearance: reject jobs requiring an active/obtainable government security clearance or clearance eligibility when that requirement effectively requires citizenship. Do not reject generic background checks.
- Location: reject jobs whose authoritative location is outside the United States. Unknown location must be resolved before Ready to Apply rather than guessed.

Hard constraints are fail-closed at the final eligibility gate: ambiguity that materially affects eligibility is resolved from the authoritative employer JD or held for retry/manual resolution, not silently accepted.

## 4. Resume decision

Fixed facts come from the master resume only: candidate identity/contact details, employer names, employment dates, education and other immutable history.

1. Extract usable JD requirements/targets from the authoritative posting.
2. If the JD is missing/insufficient or yields too few usable targets to support truthful tailoring, use the master resume unchanged and continue the job to Ready to Apply when all eligibility gates pass.
3. Otherwise generate a job-specific resume. Technical skills and experience bullets must be grounded in the JD and remain consistent with the candidate's fixed history.
4. Domain coherence is mandatory:
   - Fidelity Investments: financial/trading/market/risk/compliance data context.
   - Cigna Healthcare: healthcare, claims, eligibility, member/EHR/HIPAA context.
   - Target Corporation: retail/e-commerce/POS/sales/inventory/merchandising context.
5. Bullets must be meaningful, recruiter-readable, ATS-friendly and not keyword stuffing. Never invent a new employer, date, degree, certification or other fixed fact.
6. Generate DOCX and PDF with the established reference formatting. Artifact generation failures must not corrupt or cross-contaminate another job's resume.
7. ATS/job-fit scoring is diagnostic and optimization feedback, not permission to fabricate claims. Aim for strong JD coverage; do not claim a guaranteed 95% score from third-party ATS systems.

## 5. Ready-to-Apply and dashboard

Only jobs that pass authoritative eligibility and have a valid resume artifact (tailored or master fallback) enter Ready to Apply. The hosted Railway dashboard consumes that queue. Run snapshots must reconcile discovered, filtered, finalized, resume-ready and Ready-to-Apply counts and preserve per-job/per-run identity.

## 6. Runtime and reliability

- A production workflow has a 55-minute outer cap but must reserve time for reports, dashboard sync and artifact persistence.
- The critical production runner should finish within ~45 minutes. Expensive source-health audits and employer-universe enrichment run outside the critical path.
- Do not apt-install large OS packages such as LibreOffice on every production cycle; use a prebuilt environment or artifact fallback/recovery.
- Network collectors use bounded timeouts/concurrency. A slow source may be deferred, but its successful watermark must not advance until that source unit completes.
- A replacement cycle may cancel a stale cycle; state/artifacts should still be uploaded on failure/cancellation when GitHub permits the finalizer to run.

## 7. Observability

Every run report should show, at minimum: source/provider units attempted/succeeded/failed/deferred, employers visited, raw jobs discovered, unique jobs, US-location rejects, data-family rejects, experience rejects, sponsorship rejects, citizenship/clearance rejects, JD-resolution failures, finalized jobs, resume outcomes, Ready-to-Apply jobs, per-source watermark status and runtime by major phase. This is required to explain why a friend's same-day posting was or was not found without guessing.
