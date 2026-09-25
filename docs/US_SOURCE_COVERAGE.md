# U.S. Job Source Coverage Manifest

This manifest is the governing source-coverage plan for the production job-search agent.

## Governing rule

`data/job_sources.json` is a seed list, never an employer allowlist. A U.S. employer does not need to be preconfigured to enter discovery. Broad discovery results must be resolved to the employer's authoritative ATS/career posting when possible, and newly identified ATS boards must be learned for future direct scans.

A provider is not considered WORKING merely because its URL can be recognized. WORKING means the collector can discover a known live posting, retrieve enough authoritative job data for finalization, and send the job through the standard eligibility pipeline.

## Tier 1 — direct ATS / career platforms

Provider-specific collectors should be preferred for:
Greenhouse; Greenhouse EU; Lever; Ashby; Workday; SmartRecruiters; Eightfold; Oracle Recruiting Cloud; Taleo; SAP SuccessFactors; iCIMS; Phenom; Avature; UKG/UltiPro; Dayforce; ADP Workforce Now; Workable; Jobvite; Cornerstone; Paylocity; Paycom; BambooHR; Teamtailor; Recruitee; JazzHR/ApplyToJob; BreezyHR; Rippling; Pinpoint; BrassRing; CareerPlug; Freshteam; JobScore; Personio; Comeet; ClearCompany; ApplicantPro; Fountain; Hirebridge; Zoho Recruit; Manatal; JOIN; Applitrack/Frontline; Hireology; Paycor; PeopleAdmin; iSolved; HiBob; GoHire; HiringThing; Homerun; PageUp; TriNet; Dover; Gem; Polymer; HireHive; Kula; Rival; WeRecruit; Deel; FirstStage; TalentBrew; Radancy; Paradox; Bullhorn; JobDiva; Recruiting.com.

## Tier 2 — broad U.S. discovery portals

Use accessible portals for discovery and freshness, then prefer the authoritative employer/ATS posting for final eligibility and resume generation:
Dice; ZipRecruiter; Indeed; LinkedIn Jobs; Glassdoor; Monster; CareerBuilder; Built In; Wellfound; SimplyHired; Handshake and relevant specialist boards.

A portal result alone must not bypass authoritative-JD resolution when an employer posting can be identified.

## Tier 3 — employer career sites

Support public company career pages that are not on a recognized ATS. Generic crawling is fallback coverage, not proof that an ATS provider is supported.

## Continuous expansion

Every discovered job should be inspected for an ATS/career-system signature. Unknown boards should be recorded in the learned source registry. Learned sources must be eligible for subsequent direct discovery without requiring a manually maintained target-company list.

## Standard downstream gates

All sources feed the same pipeline:
1. Data Engineering role-family relevance.
2. United States location.
3. Full-time/permanent W-2 target; reject contract/C2C/1099/temporary.
4. Resolve authoritative complete JD and confirm the job is live.
5. Experience-level compatibility.
6. Future sponsorship / H-1B compatibility and explicit OPT/STEM restrictions.
7. Citizenship and clearance restrictions.
8. Duplicate and previously-applied suppression.
9. Resume generation only after all gates pass.
10. Resume quality/ATS audit.
11. Ready-to-Apply queue.

## Coverage status semantics

- WORKING: known live regression posting successfully discovered and processed.
- PARTIAL: collector works for some tenants/boards but has known failures.
- FALLBACK: generic crawler only; no provider-specific adapter.
- CONFIGURED: seed exists but successful collection is not yet proven.
- BLOCKED: provider/tenant currently prevents reliable automated public collection.
- DISABLED: intentionally not used.

The source-health report and dashboard should use these meanings so zero-return providers cannot appear healthy solely because a request returned HTTP 200.

## Priority implementation order

1. Eightfold
2. UKG/UltiPro
3. ADP Workforce Now
4. Avature
5. Phenom
6. Paylocity
7. Workable
8. JazzHR
9. Oracle / SuccessFactors / iCIMS
10. Dayforce / Cornerstone / Jobvite
11. remaining long-tail ATS families
12. additional broad U.S. discovery portals where technically accessible and permitted

## Completion criterion

Source expansion is not complete based on provider count. It is complete only when major U.S. ATS families have verified collectors or explicitly documented limitations, broad discovery is not constrained to a fixed employer list, learned ATS boards persist automatically, and a regression suite demonstrates discovery-to-eligibility behavior on representative live postings.
