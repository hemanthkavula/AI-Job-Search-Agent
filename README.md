# AI Job Search Agent

A source-agnostic U.S. Data Engineering job-search agent for broad discovery, eligibility verification, full-JD retrieval, truthful JD-tailored resume generation, internal ATS/evidence/quality auditing, application tracking, and eventual supported ATS submission.

## Production objective

Run every hour from **7:00 AM through 6:00 PM**, process newly posted Data Engineering roles from the prior 24 hours, avoid duplicates, prepare/apply to eligible roles, and produce an end-of-day report after the final cycle.

The system is **not company-specific**. Company/title debug flags (for example Quest Diagnostics) exist only for controlled testing.

## Current stage

The core discovery → eligibility → full-JD → resume → audit pipeline is functional and being validated. Broad dynamic discovery, persistent cross-hour orchestration, universal ATS application adapters, the 07:00–18:00 scheduler, and the automated daily report are not yet production-complete.

See **[PROJECT_STATUS.md](PROJECT_STATUS.md)** for the full architecture, completed work, current limitations, latest validation results, daily schedule, application policy, and implementation roadmap.

## Core workflow

```text
Broad discovery
→ <=24h freshness
→ U.S. + Full-Time/W2 + DE-family filters
→ experience/sponsorship/citizenship checks
→ deduplication
→ complete original JD
→ final eligibility
→ deterministic JD/evidence coverage plan
→ strongest tailored V1 resume
→ ATS/evidence/human-quality audit
→ retry only exact failed gates (max 3)
→ DOCX/PDF after pass
→ READY_TO_APPLY
→ supported ATS submission / manual-action state
→ persistent ledger
→ daily report
```

There is no JD-match-score discovery gate: an otherwise eligible job is tailored rather than rejected because the base resume has a low keyword match.

## Supported discovery adapters today

Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Dice, and ZipRecruiter adapters exist. The current ATS registry includes a finite company set, so broad dynamic discovery is the next major discovery milestone; the project does not claim universal internet coverage today.

## Safety and accuracy

The agent must never invent employers, dates, education, certifications, technologies, metrics, business outcomes, or answers to employer screening questions. Explicit no-future-sponsorship, incompatible citizenship, and clearance requirements are hard eligibility stops. Unknown sponsorship continues under the configured candidate policy.
