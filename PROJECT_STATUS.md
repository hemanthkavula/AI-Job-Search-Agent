# AI Job Search Agent — Project Status & Production Plan

**Owner:** Hemanth Kavula  
**Target:** U.S. Data Engineering roles  
**Daily operating window:** 7:00 AM–6:00 PM local time, hourly, with an end-of-day report after the final cycle.

## 1. Product objective

Build a source-agnostic job-search agent that continuously discovers newly posted U.S. Data Engineering roles, verifies eligibility, retrieves the complete employer job description, creates a truthful JD-tailored resume, validates it with internal ATS/evidence/quality gates, and ultimately submits supported applications and reports the day's activity.

The agent must not be tied to Quest Diagnostics, a fixed company list, or a single job board. Company-specific debug flags are test controls only.

## 2. Daily production behavior

Production cadence:

- 07:00 — discovery/application cycle
- 08:00 — discovery/application cycle
- 09:00 — discovery/application cycle
- 10:00 — discovery/application cycle
- 11:00 — discovery/application cycle
- 12:00 — discovery/application cycle
- 13:00 — discovery/application cycle
- 14:00 — discovery/application cycle
- 15:00 — discovery/application cycle
- 16:00 — discovery/application cycle
- 17:00 — discovery/application cycle
- 18:00 — final discovery/application cycle, then daily report

Every cycle must deduplicate against jobs already seen/processed so the same opening is not repeatedly tailored or submitted.

## 3. Target job family

Accept the Data Engineering family, including:

- Data Engineer
- Senior / Sr Data Engineer
- Lead Data Engineer
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
- Data Platform Engineer when the responsibilities are genuinely data-engineering aligned

Reject unrelated analyst, data scientist, frontend, QA, software-only, ML engineer, DevOps/SRE, DBA, architect, BI-developer, internship, and junior roles.

## 4. Candidate eligibility policy

Candidate experience target: approximately 5 years. Job requirement window: normally 4–8 years, with ranges evaluated by their minimum requirement.

Employment:
- U.S. roles only
- Full-Time or W-2
- reject explicit C2C/1099, part-time, internship, temporary, seasonal, and incompatible contract roles

Work authorization:
- currently authorized in the U.S. under F-1 OPT
- sponsorship needed now: NO
- future H-1B sponsorship: YES
- explicit no current/future sponsorship: reject
- sponsorship available: continue
- sponsorship not mentioned/unknown: continue
- explicit U.S.-citizenship or incompatible clearance requirement: reject

## 5. Correct end-to-end architecture

```text
Broad source discovery
    ↓
Source-side Data Engineering + freshness filtering where supported
    ↓
Normalize postings into one common job schema
    ↓
Freshness verification: posted within last 24 hours
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
Cross-source + historical deduplication
    ↓
PRELIMINARY_ELIGIBLE
    ↓
Resolve to original employer ATS/career posting when possible
    ↓
Retrieve COMPLETE JD
    ↓
Re-run final eligibility using complete JD
    ↓
FINAL_JD_VERIFIED
    ↓
Build deterministic JD requirement/evidence coverage plan
    ↓
Generate strongest truthful tailored resume V1
    ↓
Internal ATS + evidence + human-quality audit
    ↓
PASS → DOCX + PDF → READY_TO_APPLY
FAIL → exact audit feedback → regenerate (maximum 3 total attempts)
    ↓
Persistent failure → HOLD_ATS_REVIEW
    ↓
Application adapter
    ↓
SUBMITTED / MANUAL_ACTION_REQUIRED / APPLICATION_ERROR
    ↓
Persistent application ledger
    ↓
18:00 daily report
```

There is deliberately **no JD-match-score discovery gate**. An otherwise eligible job is not discarded merely because the base resume has a low keyword match. Tailoring happens after full-JD verification.

## 6. Discovery strategy: broad, not fixed-company only

### Current implementation

The repository currently has adapters for:
- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Workday
- Dice
- ZipRecruiter

The ATS configuration currently contains a finite set of known companies/boards. Therefore the current discovery layer is **not yet broad enough to claim coverage of every Data Engineering opening**.

### Required production design

Discovery must use multiple complementary channels:

1. **Provider-wide/job-board search** — query broad job indexes for the Data Engineering family, U.S., and recent postings.
2. **ATS discovery/resolution** — when a board result is found, resolve it to the employer's original Greenhouse/Lever/Ashby/Workday/SmartRecruiters/iCIMS/direct-career posting whenever possible.
3. **Known ATS registry** — retain direct company ATS connectors because they are useful and authoritative, but treat them as one channel rather than the universe of companies.
4. **Expandable source registry** — newly discovered employer ATS endpoints should be reusable on later hourly cycles.
5. **Canonical deduplication** — merge the same employer opening found through multiple sources.
6. **Source health telemetry** — report source failures instead of silently reducing coverage.

No implementation can truthfully guarantee literally every job on the internet: some sites block automation, have no stable interface, require authentication, or prohibit automated submission. The production objective is the broadest reliable, permitted coverage across supported sources, with original-employer postings preferred.

## 7. Full-JD rule

A lightweight search result is not enough for resume generation.

Current safeguard:
- only `FINAL_JD_VERIFIED` jobs enter `batch_prepare`
- complete JD must be marked `description_complete`
- minimum complete-JD length safeguard is 1,200 characters
- final eligibility is rerun after retrieving the complete JD

This was added after a Quest test used a truncated Dice excerpt and produced misleading ATS results.

## 8. Resume tailoring contract

Fixed identity/chronology must never change.

### Fidelity Investments — Senior Data Engineer — Jan 2025–Present
- financial-services domain only
- exactly 8 bullets
- maximum 2 metric-bearing bullets

### Cigna Healthcare — Data Engineer — Jan 2022–Dec 2023
- healthcare domain only
- exactly 7 bullets
- maximum 2 metric-bearing bullets

### Target Corporation — Data Engineer — Jan 2020–Dec 2021
- retail/e-commerce domain only
- exactly 6 bullets
- no fabricated metrics

Education:
- MS Computer Science, Rowan University, Jan 2024–Dec 2025

Output:
- `Hemanth_Kavula_{Company}_{JobTitle}.docx`
- PDF only after all release gates pass

## 9. Candidate technology evidence

The candidate profile currently records broad hands-on skills including Python, SQL, PySpark/Spark, AWS Glue/EMR/S3/Redshift/Lambda/Kinesis, Azure Data Factory, Azure Synapse Analytics, ADLS Gen2, Event Hub, Databricks, Snowflake, Kafka, Airflow, dbt, Terraform, Docker, Great Expectations, Azure Purview, BigQuery, Dagster, Apache Beam, Apache Flink, Kubernetes, ArgoCD, Helm, and Istio.

A skill being in the master inventory is permission to use it when relevant; it is **not** an instruction to stuff every skill into every resume. The next coverage-planner revision must map every material JD requirement to candidate evidence before V1 and deliberately include supported, relevant requirements.

## 10. ATS/resume quality pipeline

Current release targets:
- internal ATS score >= 95
- technology evidence >= 95
- human quality >= 90
- structure gate = pass
- metric gate = pass
- repetition gate = pass
- technology-evidence gate = pass

Maximum resume attempts: 3.

The internal ATS score is a project heuristic, not a guaranteed score from an employer's proprietary ATS.

### Latest Quest validation

Latest test:
- V1: ATS 92, Evidence 88, Human 100
- V2: ATS 100, Evidence 91, Human 100
- V3: ATS 97, Evidence 100, Human 100

V3 still held because:
- keyword coverage = 93%
- missing target = Azure Synapse Analytics
- metrics gate failed because the generated bullet contained unsupported `sub-minute` latency wording

The writer has since been instructed not to invent bounded/near-numeric latency or scale claims.

The remaining design issue is not Quest-specific: the coverage planner must classify JD requirements and map them to the master candidate evidence inventory **before** the paid V1 generation. This prevents a supported JD skill such as Azure Synapse Analytics from being accidentally omitted.

## 11. Application stage

### Intended automatic answers
- Authorized to work in the United States? **Yes**
- Require sponsorship now? **No**
- Require sponsorship now or in the future? **Yes**
- Future sponsorship required? **Yes**

Standard explanation:
“I am currently authorized to work in the United States under F-1 OPT and do not require sponsorship at this time. I will require H-1B sponsorship in the future to continue working in the United States.”

### Current status

Automatic ATS/browser submission is **not yet production-complete**. The current pipeline prepares and audits applications; it does not yet provide a universal submission adapter for every employer ATS.

Production application adapters must safely handle:
- account/login requirements
- resume upload
- contact information
- standard work-authorization questions
- job-specific screening questions
- required attestations
- CAPTCHA/MFA/manual-intervention states
- submission confirmation
- duplicate-application prevention

The agent must never invent answers to employer screening questions.

## 12. Daily report specification

After the final 18:00 cycle, produce one report containing:

- sources queried and source failures
- jobs discovered
- fresh jobs verified <=24h
- duplicates removed
- jobs rejected by reason
- preliminary eligible jobs
- full JDs successfully resolved
- final eligible jobs
- resumes generated
- V1 pass count
- retries used
- ATS holds
- applications submitted
- applications requiring manual action
- application errors
- company/title/application URL
- resume file used
- final internal ATS/evidence/human scores
- sponsorship classification
- timestamp/status for each application

## 13. Persistent state requirements

Hourly operation requires persistent state, not independent stateless searches. Store:
- canonical job ID / employer requisition ID
- source IDs and original ATS URL
- first seen / posting time / last seen
- eligibility decision and reasons
- JD hash/version
- resume path/version
- audit result
- application status
- submission confirmation
- retry/error history

This prevents duplicate resumes and duplicate applications across hourly and daily runs.

## 14. Current project stage

| Component | Status |
|---|---|
| Candidate profile | Implemented |
| Strict DE-family filtering | Implemented |
| U.S./employment filtering | Implemented |
| Experience screening | Implemented |
| Sponsorship policy | Implemented |
| Citizenship/clearance rejection | Implemented |
| <=24h freshness framework | Implemented |
| Cross-query discovery dedup | Implemented |
| Greenhouse adapter | Implemented |
| Lever adapter | Implemented |
| Ashby adapter | Implemented |
| SmartRecruiters adapter | Implemented |
| Workday adapter | Implemented |
| Dice discovery | Working in tests |
| ZipRecruiter | Adapter exists; provider reliability still needs validation |
| Full-JD finalizer | Implemented |
| Final eligibility after full JD | Implemented |
| JD coverage plan | Implemented, needs evidence/classification upgrade |
| LLM resume generation | Implemented |
| Exact 8/7/6 resume structure | Implemented |
| DOCX formatting | Implemented |
| ATS/evidence/human audit | Implemented, still being calibrated semantically |
| Quality-driven max-3 retry | Implemented |
| PDF after pass only | Implemented |
| Broad dynamic source discovery | **Not complete** |
| Persistent cross-hour application ledger | **Needs production hardening** |
| Universal ATS auto-application | **Not complete** |
| 07:00–18:00 hourly scheduler | **Not complete** |
| 18:00 daily report automation | **Not complete** |
| End-to-end unattended production run | **Not ready yet** |

**Overall stage:** core discovery/filter/final-JD/resume/audit pipeline is functional and under validation. The project is currently between **resume-quality validation** and **production orchestration/application automation**.

## 15. Next implementation order

1. Fix the deterministic coverage planner so every material JD requirement is classified as required/preferred/alternative and mapped to candidate evidence before V1.
2. Revalidate V1 on several different JDs (AWS-heavy, Azure-heavy, platform-heavy), not just Quest.
3. Replace fixed-company dependence with broad provider/job-board discovery plus original-ATS resolution and an expandable ATS registry.
4. Add persistent job/application ledger and cross-hour deduplication.
5. Build application adapters and explicit manual-action states for unsupported/CAPTCHA/MFA flows.
6. Add one production cycle command that runs discovery → finalization → tailoring → audit → application → ledger.
7. Add scheduler for hourly cycles from 07:00 through 18:00.
8. Add end-of-day report after the 18:00 cycle.
9. Run in dry-run mode across multiple days.
10. Enable unattended submissions only after application adapters and safeguards pass validation.

## 16. Definition of done

The agent is production-ready when a single scheduled workflow can run hourly from 07:00–18:00, discover broad current Data Engineering openings without relying on a fixed company list, verify complete JDs and eligibility, generate truthful job-specific resumes, pass release gates, submit through supported ATS flows, persist confirmations, avoid duplicates, surface manual-only cases, and produce a complete daily report after the final cycle.
