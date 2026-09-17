# Job Source Coverage

The agent prioritizes official/public ATS and job-search interfaces and avoids brittle or unauthorized scraping.

## Active discovery sources

- Dice official MCP — US, Full-Time, posted within one day, Data Engineering family searches.
- ZipRecruiter official MCP — US, Full-Time, one-day recency, Data Engineering family searches, offset pagination.
- Workday public CXS career sites — verified company career sites configured in `data/job_sources.json`.
- Ashby public Job Posting API — verified company boards configured in `data/job_sources.json`; exposes `publishedAt`, employment type, location and full description.
- SmartRecruiters public company APIs — verified company career sites configured in `data/job_sources.json`.
- Greenhouse public Job Board APIs — verified company boards configured in `data/job_sources.json`.
- Lever public Postings API — verified company sites configured in `data/job_sources.json`.

## Freshness policy

A job can enter the eligibility/resume pipeline only when the source supplies a trustworthy posting/publication timestamp that verifies it was posted within the configured window (24 hours by default). `first_seen` is never used as proof of posting age.

Some public ATS interfaces do not expose a reliable publication timestamp for every posting. Those postings may be discovered for diagnostics, but the strict freshness gate must reject them until an authoritative timestamp is available.

## LinkedIn

LinkedIn does not provide an unrestricted public job-search API for this standalone agent. LinkedIn Talent Solutions APIs are restricted to approved partners, and the Job Posting API is for posting/integration workflows rather than unrestricted public job search. The project therefore does not use unofficial LinkedIn scraping or private endpoints. LinkedIn results can be added later only through an authorized interface that permits job-search retrieval.

## Indeed

Indeed's documented APIs are partner/authorized integrations. The Job Sync API is primarily for ATS partners to create/manage postings; job-retrieval access is permissioned. The standalone agent therefore does not pretend to have unrestricted Indeed API access. An authorized Indeed connection can be added when access is available.

## Monster / Jobright

No stable official public job-search API has been verified for this standalone agent. Do not add private/undocumented scraping endpoints. If an official supported API/MCP becomes available, add it as a discovery adapter and preserve the same hard eligibility/freshness gates.

## Optional future sources requiring credentials

USAJOBS has an official Search API with title/keyword, full-time schedule, date-posted, location and pagination filters, but requires a USAJOBS API key and the registration email in request headers. It can be added when credentials are intentionally configured. Federal eligibility requirements should remain a separate hard eligibility concern.

## Source strategy

1. Search/filter at the source whenever supported.
2. Keep only the Data Engineering title family.
3. Require authoritative <=24-hour freshness.
4. Require US and Full-Time/W2.
5. Check experience eligibility.
6. Reject only explicit sponsorship incompatibility; unknown/not-mentioned sponsorship proceeds.
7. Retrieve/use the complete employer JD before resume tailoring.
8. Prefer the original employer ATS/career posting over aggregator copies whenever it can be resolved safely.
