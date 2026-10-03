# Application Stage Rollout

The automated application executor is invoked by the production workflow only after production acceptance succeeds.

The executor is deliberately fail-safe:

- discovery/resume work remains valid if browser setup or an individual application fails;
- `SUBMITTED_CONFIRMED` requires visible post-submit confirmation;
- an ambiguous submit is recorded as `SUBMISSION_ATTEMPTED` and is never retried by clicking Submit again in the same run;
- CAPTCHA/MFA/authentication and unknown required answers become manual-action states;
- explicit no-sponsorship language proceeds, while citizenship and clearance restrictions remain blockers;
- duplicate submitted requisitions are skipped from persistent ledger state.

A zero-job cycle still marks the application stage enabled with zero processed applications, without importing or launching the browser runtime.
