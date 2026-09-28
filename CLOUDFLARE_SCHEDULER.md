# Cloudflare production scheduler

This Worker is an external clock for the existing GitHub Actions production workflow.

## Schedule
Cloudflare cron heartbeats wake at the configured UTC times. The Worker converts each scheduled timestamp to America/New_York and dispatches GitHub only during the 55-minute recovery windows for 07:30, 10:00, 12:30, 15:30, 18:30, and 21:00 ET.

The GitHub/Python pipeline keeps its existing `last_completed_slot` protection, so recovery dispatches do not intentionally process a completed slot twice.

## Required Cloudflare secret
Set `GITHUB_DISPATCH_TOKEN` as a Worker secret. Use a fine-grained GitHub token scoped only to `hemanthkavula/AI-Job-Search-Agent` with Actions: Read and write.

Never commit the token to this repository.

## Deploy
`npx wrangler secret put GITHUB_DISPATCH_TOKEN`
`npx wrangler deploy`
