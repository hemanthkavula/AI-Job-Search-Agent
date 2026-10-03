# Application Stage Status Semantics

- `SUBMITTED_CONFIRMED`: final Submit was clicked once and visible employer/ATS confirmation was observed.
- `SUBMISSION_ATTEMPTED`: Submit may have been sent but the outcome is ambiguous; never click Submit again automatically in the same run.
- `MANUAL_ACTION_REQUIRED`: CAPTCHA/MFA/authentication, unknown required answer, missing validated resume, or unrecoverable application interaction.
- `PERMANENT_SKIP`: citizenship/clearance incompatibility discovered during the application UI.
- `READY_TO_APPLY`: remains retryable when browser runtime setup is unavailable.
