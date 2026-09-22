# AI Job Search Agent

A production-oriented U.S. Data Engineering job-search system that discovers jobs, applies strict eligibility rules, retrieves complete job descriptions, generates JD-specific resumes, validates resume quality, builds a manual application queue, and syncs the queue to a persistent hosted dashboard.

## Current production flow

```text
Scheduled cloud trigger
→ broad multi-source discovery
→ freshness + deduplication
→ U.S.-only / Data-Engineering-family eligibility
→ Full-Time / W-2 eligibility
→ sponsorship / citizenship / clearance checks
→ complete original JD retrieval and verification
→ final eligibility
→ JD-driven resume generation
→ ATS + evidence + recruiter + human-quality validation
→ targeted retry when a validation gate fails
→ validated DOCX/PDF artifacts
→ READY_TO_APPLY
→ persistent application queue
→ hosted dashboard sync
→ user manually opens employer application and submits
→ user marks application Applied
→ applied status + resume reference remain persistent
```

Application submission is intentionally manual. The production agent prepares qualified applications and resumes but does not autonomously submit employer applications.

## Production schedule and reliability

Production runs Monday-Friday in **America/New_York** at seven two-hour slots:

**7 AM, 9 AM, 11 AM, 1 PM, 3 PM, 5 PM, and 7 PM Eastern.**

Each intended slot now has **six independent GitHub Actions trigger opportunities at :07, :17, :27, :37, :47, and :57**. The :07 event is the primary trigger. Every later event is a watchdog: it checks whether another run in that slot is already queued, running, or successful and exits as a no-op when the slot is healthy. If the earlier trigger was dropped or the run failed, the next watchdog executes recovery. This substantially reduces dependence on any single scheduled event.

Persistent scheduler and per-source watermarks provide another recovery layer. A missed or failed discovery interval is resumed from the last successful watermark instead of silently advancing past it. Workday tenants maintain independent watermarks so one failing tenant does not prevent healthy tenants from advancing.

The reliability model is therefore:

```text
Primary scheduled trigger
→ watchdog recovery
→ persistent watermark catch-up
```

## Eligibility policy

The production pipeline targets U.S. Data Engineering roles, including Data Engineer, Senior Data Engineer, Staff Data Engineer, Principal Data Engineer, cloud-focused Data Engineer roles, and legitimate closely related individual-contributor Data Engineering roles.

Hard filtering includes:

- United States roles only. Onsite, hybrid, and U.S.-scoped remote roles are allowed.
- Data Engineering role family only.
- Full-time / W-2 focus.
- Reject when the posting explicitly says current or future employment sponsorship is unavailable.
- Reject explicit U.S.-citizenship requirements.
- Reject roles requiring a security clearance.
- Reject non-IC Manager, Director, Architect, and Consultant role families even when the title contains Data Engineering terminology.
- Unknown sponsorship status is not automatically rejected.

## Discovery

The system supports discovery across configured and learned sources including:

- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Workday
- SuccessFactors
- iCIMS
- Oracle
- company career sites
- Eightfold
- Dice
- ZipRecruiter

Discovery state is persisted across cloud runs so providers resume from their own successful watermarks rather than relying on a single global time window.

## JD-specific resume generation

The complete verified job description is the primary source for the tailored resume's technical content.

The master candidate profile is used as the factual identity and chronology anchor for fixed information such as contact information, employers/clients, job titles, locations, employment dates, education, and existing certifications.

For each eligible job, the resume generator:

1. extracts the material requirements, technologies, tools, platforms, and responsibilities from the JD;
2. prioritizes those requirements in the Summary and Technical Skills;
3. demonstrates important JD technologies and responsibilities naturally within relevant experience sections while preserving employer/domain context;
4. preserves fixed chronology and identity facts;
5. does not invent employers, titles, dates, locations, education, certifications, unsupported numerical metrics, or named business/project outcomes.

The system does **not** use the master resume's existing technical bullet content as a whitelist for JD tailoring.

## Resume validation

Generated resumes pass through automated quality gates before they can enter the application queue. Validation covers JD requirement coverage, ATS-oriented structure/coverage, experience depth, evidence consistency, recruiter readability, human-quality checks, and DOCX/PDF artifact validation.

Failed resumes are retried against the specific failed gates rather than blindly regenerated. A job reaches `READY_TO_APPLY` only after the required resume and artifact checks pass.

There is no artificial production resume-count cap: all jobs that qualify in a production cycle can proceed through resume generation and validation, subject to normal runtime/API constraints.

## Hosted application dashboard

The persistent hosted dashboard displays the application pipeline and remains available independently of the user's laptop.

For each queued application it can show:

- company and role
- application status
- source / portal
- validated resume PDF
- employer application link
- applied date/status

The user opens **Open job / Apply**, completes the employer application manually, and then selects **Mark Applied**. Applied status is persisted independently of subsequent production syncs. The associated resume reference is also preserved, with recovery support for older applied records whose current ledger entry no longer contains the PDF path.

## Automation boundary

The automated production boundary is:

```text
Discover
→ qualify
→ retrieve/verify JD
→ generate + validate resume
→ queue
→ sync dashboard
```

The final employer submission remains a user action. The system does not run autonomous browser submission agents.

## State and cloud operation

Scheduled production runs in GitHub Actions. Generated scheduler state, discovery state, ledger data, resume artifacts, and queue data are carried across runs and synchronized to the hosted dashboard. The dashboard stores its persistent state on its attached volume, so normal service deployments do not intentionally reset application history.

The laptop does not need to remain on for scheduled discovery, resume generation, queue creation, dashboard synchronization, or watchdog recovery.

## Safety and accuracy

The system must not fabricate fixed candidate facts, employers, chronology, education, certifications, numerical achievements, or screening-question answers. Eligibility decisions preserve explicit evidence from the posting, and failed source scans retain their previous watermark so transient provider failures do not silently create discovery gaps.

See **[PROJECT_STATUS.md](PROJECT_STATUS.md)** for implementation-level status and historical validation details.
