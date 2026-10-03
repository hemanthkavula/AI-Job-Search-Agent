# Cloudflare scheduler

Cloudflare is the primary external clock for both scheduler families. GitHub Actions keeps native scheduled fallbacks so one missed Cloudflare dispatch does not silently drop either enrichment or a production window.

## Employer/source enrichment
Monday-Friday at 05:30 America/New_York, Cloudflare dispatches `.github/workflows/employer-universe-enrichment.yml`.

That workflow runs employer/source enrichment only. It may verify employer domains, career pages, ATS families, and ATS tenant/source metadata and persist the learned source state. It does **not** run the production job cycle, generate resumes, create application records, or update the job dashboard.

Cloudflare wakes at both possible UTC equivalents of 05:30 ET (09:30 during EDT and 10:30 during EST). The Worker converts to `America/New_York` and dispatches only when the local time is exactly 05:30 on a weekday.

GitHub Actions retains its own 09:30/10:30 UTC weekday schedule as an independent fallback. The workflow's local-time guard prevents the inactive DST alternative from doing enrichment work.

## Production job cycles
The requested production slots are Monday-Friday at 07:30, 10:00, 12:30, 15:30, 18:30, and 21:00 America/New_York.

Cloudflare wakes three times per hour on Monday-Saturday UTC. The Worker converts each heartbeat to America/New_York and dispatches `daily-discovery.yml` only during the 55-minute recovery windows for those six requested ET slots. Saturday UTC coverage is intentional because Friday 21:00 ET occurs after UTC has rolled into Saturday.

GitHub Actions also schedules fallback heartbeats shortly after every production slot for both EDT and EST UTC offsets. The workflow performs the same America/New_York slot check before doing production work, so the inactive DST alternative exits as a no-op.

The GitHub/Python pipeline keeps `last_completed_slot` protection. Cloudflare retries and GitHub fallback heartbeats therefore share the same idempotency guard and do not intentionally process an already completed production slot twice. Partial cycles remain retryable inside the same recovery window because only a fully successful cycle closes the slot.

## Required Cloudflare secret
Set `GITHUB_DISPATCH_TOKEN` as a Worker secret. Use a fine-grained GitHub token scoped only to `hemanthkavula/AI-Job-Search-Agent` with Actions: Read and write.

Never commit the token to this repository.

## Deploy
`npx wrangler secret put GITHUB_DISPATCH_TOKEN`
`npx wrangler deploy`
