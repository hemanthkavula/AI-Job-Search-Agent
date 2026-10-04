# Current Source-to-Dashboard Contract

This file records the user-authoritative production contract as of 2026-10-04.

## Terminal boundary

Automation ends at the dashboard/application-ready queue. The system must not submit applications on the user's behalf.

## Flow

1. Discover U.S. Data Engineering-family jobs from configured employer ATS sources, direct career sites, and job-board discovery sources, using source-specific watermarks/timestamps so successful sources advance independently and failed sources can catch up.
2. Prefer the employer ATS/career posting as the authoritative source for the final JD and official posting date. Job-board repost timestamps do not override an older employer posting date.
3. Apply eligibility filters after broad discovery. Current hard filters include U.S. location, Data Engineering-family relevance, accepted employment type, inclusive 4-7 year required-experience window, citizenship-only restrictions, and required security-clearance restrictions. Sponsorship is not an eligibility filter.
4. Resolve and verify the full/usable JD for surviving jobs.
5. Build a deterministic JD coverage/target plan.
6. If target_count == 0, use the user-uploaded authoritative master resume unchanged.
7. If target_count >= 1, generate a JD-specific tailored resume. The JD/coverage plan is the only technical-content source. The master resume contributes only fixed personal/history facts: identity/contact information, employer names, titles, locations, dates, and education.
8. Every tailored resume must preserve the master resume's measured visual format: Calibri typography, sizes, colors, spacing, section structure, right-aligned dates, Roles & Responsibilities labels, Environment lines, 10/8/8 employer bullet counts, selective bold emphasis in summary/bullets, and the Fidelity page continuation pattern.
9. Run ATS/content quality audits. Failed tailored resumes may be regenerated up to the configured retry limit using only JD-derived technical content. A zero-target master resume is never converted into a tailored resume merely because an audit fails.
10. Convert the approved DOCX to PDF and validate DOCX/PDF parity.
11. Only audit-approved and artifact-valid jobs enter READY_TO_APPLY / the application-ready queue.
12. Sync the resulting jobs/resumes to the dashboard. Do not auto-submit applications.

## Master resume authority

The authoritative master is represented by `data/master_resume.json` and fingerprinted from the user-uploaded file `Hemanth_Kavula_Senior_Data_Engineer_Resume(1).pdf` with SHA-256:

`81b8a8ec35b1a21e81671d2f386aa391bbeb170e6334c0336874fd6d323353e2`

Technical content from this master must never leak into a nonzero-target tailored resume unless the same technical term independently appears in the current JD/coverage plan.
