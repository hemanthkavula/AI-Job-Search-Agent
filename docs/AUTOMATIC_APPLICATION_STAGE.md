# Automatic Application Stage

The production pipeline treats browser application execution as a post-acceptance stage. Discovery, authoritative JD verification, eligibility, resume generation, artifact validation, and `production_acceptance` must complete before any browser can apply.

## Submission policy

- Process only `READY_FOR_ATS_ADAPTER` queue rows.
- Re-run the hard eligibility gate immediately before browser execution.
- Explicit no-sponsorship / no-future-sponsorship language is not an eligibility blocker.
- U.S.-citizenship-only and security/public-trust clearance requirements remain blockers. If one appears for the first time during the application UI, stop without submitting.
- Upload only the exact validated PDF from the queue.
- Use only candidate/profile facts, queue `known_answers`, and approved `application_preferences`.
- Never invent required answers. Unknown salary, employer-specific questions, or unsupported facts become `MANUAL_ACTION_REQUIRED`.
- Never bypass CAPTCHA, MFA, verification-code, or unavoidable authentication gates.
- Final submit is permitted only in the scheduled production workflow after pre-submit validation.
- Click final Submit exactly once. A visible employer/ATS confirmation is required before recording `SUBMITTED_CONFIRMED`.
- Ambiguous post-submit state becomes `SUBMISSION_ATTEMPTED`; the executor must not click Submit again.
- Already-submitted requisitions are skipped by the persistent job ledger.

## Runtime isolation

Core discovery/resume dependencies remain in `requirements.txt`. Browser automation is isolated in `requirements-application.txt` and installed by the production workflow only when a ready application queue is non-empty.

Application-browser failures are recorded per job and do not invalidate a successful discovery cycle or prevent generated state from syncing to the dashboard.
