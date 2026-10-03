# Cloudflare production scheduler

This Worker is the primary external clock for the GitHub Actions production workflow. GitHub Actions also has a native scheduled fallback so one missed Cloudflare dispatch cannot silently drop a production window.

## Schedule
The requested production slots are Monday-Friday at 07:30, 10:00, 12:30, 15:30, 18:30, and 21:00 America/New_York.

Cloudflare wakes three times per hour on Monday-Saturday UTC. The Worker converts each heartbeat to America/New_York and dispatches GitHub only during the 55-minute recovery windows for the six requested ET slots. Saturday UTC coverage is intentional because Friday 21:00 ET occurs after UTC has rolled into Saturday.

GitHub Actions also schedules one fallback heartbeat shortly after every slot for both EDT and EST UTC offsets. The workflow performs the same America/New_York slot check before doing any production work, so the inactive DST alternative exits as a no-op.

The GitHub/Python pipeline keeps its existing `last_completed_slot` protection. Cloudflare retries and GitHub fallback heartbeats therefore share the same idempotency guard and do not intentionally process an already completed slot twice. Partial cycles remain retryable inside the same recovery window because only a fully successful cycle closes the slot.

## Required Cloudflare secret
Set `GITHUB_DISPATCH_TOKEN` as a Worker secret. Use a fine-grained GitHub token scoped only to `hemanthkavula/AI-Job-Search-Agent` with Actions: Read and write.

Never commit the token to this repository.

## Deploy
`npx wrangler secret put GITHUB_DISPATCH_TOKEN`
`npx wrangler deploy`
