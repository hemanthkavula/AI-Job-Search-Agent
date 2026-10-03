# Application Stage Idempotency

Before opening a browser, the executor checks persistent ledger state. Jobs already recorded as `SUBMITTED` or `SUBMITTED_CONFIRMED` are skipped. A single run never retries an ambiguous final Submit click.
