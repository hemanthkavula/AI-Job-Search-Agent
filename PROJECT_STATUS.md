# AI Job Search Agent — Project Status & Production Plan

**Owner:** Hemanth Kavula  
**Target:** U.S. Data Engineering roles  
**Current mode:** Cloud production pipeline with manual employer submission  
**Schedule:** Monday-Friday, 7 AM–7 PM Eastern, every two hours

## 1. Product objective

Build and operate a source-agnostic job-search agent that discovers newly posted U.S. Data Engineering roles, verifies eligibility, retrieves the complete employer job description, creates a JD-specific tailored resume, validates it with internal ATS/evidence/recruiter/human-quality gates, and publishes qualified applications to a persistent hosted dashboard.

The automated production boundary ends at a prepared application. Employer application submission remains manual.

## 2. Current production architecture

```text
Primary scheduled trigger
    ↓
Watchdog recovery if primary is missing/failed
    ↓
Persistent watermark catch-up
    ↓
Multi-source job discovery
    ↓
Freshness + canonical deduplication
    ↓
U.S. location
    ↓
Full-Time / W-2
    ↓
Data Engineering title/family
    ↓
Experience screening
    ↓
Sponsorship / citizenship / clearance screening
    ↓
PRELIMINARY_ELIGIBLE
    ↓
Resolve original employer ATS/career posting
    ↓
Retrieve and verify COMPLETE JD
    ↓
Re-run final eligibility using complete JD
    ↓
FINAL_JD_VERIFIED
    ↓
Build JD requirement/coverage plan
    ↓
Generate strongest tailored resume V1
    ↓
ATS + evidence + recruiter + human-quality audit
    ↓
PASS → DOCX/PDF artifact validation
FAIL → targeted audit feedback → regenerate, maximum 3 attempts
    ↓
READY_TO_APPLY
    ↓
Persistent application queue
    ↓
Hosted dashboard sync
    ↓
User manually opens employer application and submits
    ↓
User marks application Applied
    ↓
Persistent applied history + preserved resume reference
```

There is deliberately no JD-match-score discovery gate. An otherwise eligible job is tailored rather than rejected because the base resume has a low keyword match.

There is also no artificial production resume-count cap. All jobs that qualify for resume preparation can proceed, subject to normal API/runtime and validation constraints.

## 3. Production schedule and reliability

Production has seven intended weekday slots:

- 7 AM ET
- 9 AM ET
- 11 AM ET
- 1 PM ET
- 3 PM ET
- 5 PM ET
- 7 PM ET

Each intended production slot now has **six independent GitHub Actions trigger opportunities: :07, :17, :27, :37, :47, and :57**.

The **:07 trigger is primary**. The later triggers are watchdog retries. Before doing production work, each watchdog checks recent scheduled runs for the same slot. If another run is queued, running, or successful, it exits without duplicating production. If earlier triggers were dropped or the run failed, the next watchdog executes the production cycle in recovery mode. Later watchdogs provide additional retry opportunities if a recovery attempt itself fails.

Persistent scheduler/provider watermarks provide the final recovery layer. Missed intervals resume from the last successful watermark instead of silently advancing. Failed providers retain their previous watermark. Workday tenants maintain independent watermarks so one failing tenant does not force healthy tenants to replay the same interval.

A five-minute overlap is added around discovery windows to reduce boundary misses.

```text
Primary :07
→ Watchdogs :17 / :27 / :37 / :47 / :57
→ Watermark catch-up
```

The pipeline runs in the cloud; the user's laptop does not need to remain on.

## 4. Target job family

Accept appropriate individual-contributor Data Engineering roles, including:

- Data Engineer
- Senior / Sr Data Engineer
- Staff Data Engineer
- Principal Data Engineer
- AWS Data Engineer
- Azure Data Engineer
- Cloud Data Engineer
- Big Data Engineer
- Data Infrastructure Engineer
- Data Pipeline Engineer
- ETL Data Engineer
- Analytics Data Engineer
- genuinely Data-Engineering-aligned Data Platform Engineer roles

The current hard title guard rejects Manager, Director, Architect, and Consultant role families even when Data Engineering terminology also appears in the title.

Unrelated analyst, data scientist, frontend, QA, software-only, ML engineer, DevOps/SRE, DBA, BI-only, internship, and junior roles are outside the target family.

## 5. Candidate eligibility policy

Candidate experience target: approximately 5+ years.

Employment policy:

- United States roles only.
- U.S. onsite, hybrid, and U.S.-scoped remote roles are allowed.
- Generic “Remote” must establish U.S. scope before qualifying.
- Full-Time / W-2 focus.
- Reject explicit C2C/1099, part-time, internship, temporary, seasonal, and incompatible employment arrangements.

Work authorization policy:

- currently authorized to work in the United States under F-1 OPT
- sponsorship required now: no
- future H-1B sponsorship required: yes
- explicit no current/future sponsorship: reject
- sponsorship available: continue
- sponsorship not mentioned/unknown: continue
- explicit U.S.-citizenship requirement: reject
- required security clearance: reject

## 6. Discovery

Current production discovery includes configured and learned sources across:

- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Workday
- SuccessFactors
- iCIMS
- Oracle
- direct/company career sites
- Eightfold
- Dice
- ZipRecruiter

Newly learned Workday tenants are incorporated into scheduler tracking. Workday tenants have independent failure domains and watermarks.

Cross-source and historical deduplication prevent the same opening from being repeatedly prepared.

No implementation can guarantee every job on the public internet; the production objective is broad reliable coverage across supported sources, with original-employer postings preferred whenever they can be resolved.

## 7. Full-JD rule

A lightweight search result or job-board excerpt is not sufficient for resume generation.

Only jobs that successfully reach **FINAL_JD_VERIFIED** can enter resume preparation. Complete-JD safeguards and final eligibility checks are applied before paid resume generation.

This prevents a truncated posting excerpt from driving an inaccurate resume.

## 8. Resume tailoring contract

The master candidate profile is the fixed identity and chronology anchor, not the technical-content ceiling.

Fixed facts include:

### Fidelity Investments — Senior Data Engineer — Jan 2025–Present
- Jersey City, NJ
- financial-services/trading/risk/compliance domain
- exactly 8 bullets
- maximum 2 metric-bearing bullets

### Cigna Healthcare — Data Engineer — Jan 2022–Dec 2023
- Bangalore, India
- healthcare/claims/eligibility domain
- exactly 7 bullets
- maximum 2 metric-bearing bullets

### Target Corporation — Data Engineer — Jan 2020–Dec 2021
- Bangalore, India
- retail/e-commerce/POS/inventory domain
- exactly 6 bullets
- no fabricated numerical metrics

Education:
- MS Computer Science, Rowan University, Glassboro, NJ
- Jan 2024–Dec 2025

Output naming:
- `Hemanth_Kavula_{Company}_{JobTitle}.docx`
- corresponding PDF after release/artifact gates pass

### Current JD-driven tailoring behavior

The complete verified JD is the primary technical-content source for Summary, Technical Skills, and Experience.

Material technologies, tools, platforms, concepts, and responsibilities required by the JD are prioritized in Skills and demonstrated naturally across one or more relevant experience sections while preserving the employer's domain context.

The master resume's existing technical bullets and technical list are **not a whitelist** that restricts tailoring.

The writer must not invent employers, titles, dates, locations, education, certifications, unsupported numerical metrics, named projects, or business outcomes.

## 9. Resume quality pipeline

Current release targets include:

- internal ATS target >= 95
- JD/material-requirement coverage
- technology/evidence depth
- recruiter-quality checks
- human-quality target >= 90
- structure gate
- metric gate
- repetition gate
- artifact validation

Maximum resume attempts: 3.

Passed JD coverage is carried forward during retries so correcting one failed gate does not unnecessarily lose requirements that already passed.

Material JD platforms and technologies are deliberately represented in relevant experience where coherent, not merely keyword-stuffed into Skills.

The internal ATS result is a project heuristic and not an employer's proprietary ATS score.

## 10. Artifact validation

A resume does not enter the application queue merely because text generation succeeded.

The release process validates DOCX/PDF artifacts, including PDF generation/parity checks. Cloud GitHub Actions installs LibreOffice Writer so production artifact validation can run without the user's computer.

A job reaches **READY_TO_APPLY** only after the required resume and artifact gates pass.

## 11. Application stage

Application submission is intentionally manual.

The automated system:

```text
discovers
→ qualifies
→ verifies JD
→ generates/validates resume
→ queues
→ syncs dashboard
```

The user then opens the employer application, completes the form, submits it, and marks the job **Applied** in the hosted dashboard.

Browser/autofill agents are not part of the current production submission flow.

## 12. Hosted dashboard

The Railway-hosted Application Tracker is the persistent user-facing application queue.

It shows:

- company and role
- application status
- source/portal
- validated resume PDF when available
- employer application link
- applied status/date

**Mark Applied** stores a persistent confirmation separately from normal production ledger synchronization.

Applied records now preserve their associated resume reference. Older applied records can recover an existing validated PDF from a matching company/title ledger record when the current source record no longer carries its PDF path.

The dashboard state is stored on its attached persistent volume and synchronized from successful GitHub production cycles.

## 13. Persistent state

Production maintains state for:

- canonical job identity / requisition
- source IDs and URLs
- first/last seen timestamps
- eligibility decisions and rejection reasons
- complete-JD state
- resume paths and versions
- audit results
- queue/application state
- applied confirmations
- provider watermarks
- Workday tenant watermarks
- source failures/retry state

This prevents duplicate processing and preserves missed discovery windows across independent cloud executions.

## 14. Latest validated production results

Recent cloud production validation established:

- GitHub Actions test suite passing after scheduler/cleanup compatibility fixes.
- LibreOffice available in the cloud workflow for resume PDF validation.
- A successful manual production run produced **21 READY_TO_APPLY applications from 21 prepared jobs**, with zero resume retries in that run.
- The hosted dashboard successfully received the production queue.
- Resume PDF path remapping between ephemeral GitHub runner paths and persistent Railway state was fixed and validated.
- **Mark Applied** persistence was fixed and user-verified.
- Applied-resume PDF preservation/recovery was subsequently added and user-verified for the previously unavailable ICF and Visa PDFs.
- The scheduler uses persisted provider and Workday-tenant watermarks for catch-up.

The new :17 primary / :37 watchdog reliability behavior is the current production schedule design and should continue to be observed across scheduled cloud runs.

## 15. Current component status

| Component | Status |
|---|---|
| Candidate identity/chronology profile | Implemented |
| Strict Data Engineering family filtering | Implemented |
| Manager/Director/Architect/Consultant hard guard | Implemented |
| U.S. location filtering | Implemented |
| Employment filtering | Implemented |
| Experience screening | Implemented |
| Sponsorship policy | Implemented |
| Citizenship/clearance rejection | Implemented |
| Freshness framework | Implemented |
| Cross-source/historical deduplication | Implemented |
| Greenhouse | Implemented |
| Lever | Implemented |
| Ashby | Implemented |
| SmartRecruiters | Implemented |
| Workday + learned tenants | Implemented |
| SuccessFactors | Integrated |
| iCIMS | Integrated |
| Oracle | Integrated |
| Career-site discovery | Integrated |
| Eightfold | Integrated |
| Dice | Integrated |
| ZipRecruiter | Integrated; provider reliability can vary |
| Complete-JD finalizer | Implemented |
| Final eligibility after full JD | Implemented |
| JD-driven resume coverage | Implemented |
| LLM resume generation | Implemented |
| Exact 8/7/6 experience structure | Implemented |
| ATS/evidence/recruiter/human audit | Implemented |
| Quality-driven max-3 retry | Implemented |
| DOCX/PDF validation | Implemented |
| Process all eligible production jobs | Implemented |
| Persistent provider watermarks | Implemented |
| Workday tenant watermarks | Implemented |
| Two-hour weekday scheduler | Implemented |
| Redundant primary + watchdog schedule | Implemented; ongoing production observation |
| Persistent application ledger | Implemented |
| Hosted application dashboard | Implemented |
| Dashboard queue synchronization | Implemented |
| Manual Mark Applied tracking | Implemented and user-verified |
| Applied resume PDF preservation/recovery | Implemented and user-verified |
| Autonomous ATS/browser submission | Intentionally disabled / not production scope |
| Laptop required for production | No |

## 16. Current operational boundary

The system is now designed for unattended cloud operation through **READY_TO_APPLY** and dashboard publication.

The user does not need to keep the laptop running for:

- scheduled discovery
- filtering and final-JD retrieval
- resume generation/retries
- DOCX/PDF validation
- application queue creation
- dashboard synchronization
- watchdog recovery

Manual work remains only where intended: reviewing/opening a queued application, completing the employer's application process, and marking it Applied.

## 17. Remaining production work

The immediate work is operational validation rather than redesign of already validated components:

1. Observe the new primary/watchdog schedule over real production slots and confirm expected skip/recovery behavior.
2. Continue monitoring provider reliability and source-specific failures without advancing failed-provider watermarks.
3. Harden dashboard access/privacy before treating resume/application data as securely private on a public URL.
4. Add exact OpenAI token/cost accounting if per-cycle dollar-cost reporting is required.
5. Add/refresh end-of-day reporting if a separate daily summary remains desired.
6. Avoid changing validated discovery, filtering, resume, and queue logic without new production evidence.

## 18. Definition of current production success

A healthy scheduled slot should:

1. receive the primary trigger or automatically recover through the watchdog;
2. resume discovery from persisted source-specific watermarks;
3. discover and deduplicate supported U.S. Data Engineering jobs;
4. reject ineligible roles;
5. verify complete JDs;
6. generate and validate all eligible tailored resumes;
7. publish passing applications to the hosted dashboard;
8. preserve prior applied history and resume PDFs;
9. leave employer submission for the user.

If an external scheduled trigger or source fails, the system should preserve the unprocessed interval and retry it rather than silently losing that interval.
