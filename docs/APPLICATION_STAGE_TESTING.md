# Application Stage Testing

CI validates the application-stage policy without installing or launching a browser. This keeps ordinary source validation fast while covering sponsorship/citizenship/clearance behavior, submission-confirmation classification, ledger terminal statuses, and zero-queue behavior.

The browser dependency and Chromium runtime are installed only by the scheduled production workflow when the accepted application queue contains at least one `READY_FOR_ATS_ADAPTER` row.
