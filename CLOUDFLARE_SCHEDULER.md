# Cloudflare production scheduler

This Worker is an external clock for the existing GitHub Actions production workflow.

## Schedule
Cloudflare wakes at :07, :22, and :42 on weekdays (UTC cron). The Worker converts the scheduled timestamp to America/New_York and only dispatches GitHub during 07:00, 09:00, 11:00, 13:00, 15:00, 17:00, and 19:00 ET.

The GitHub/Python pipeline keeps its existing `last_completed_slot` protection, so recovery dispatches do not intentionally process a completed slot twice.

## Required Cloudflare secret
Set `GITHUB_DISPATCH_TOKEN` as a Worker secret. Use a fine-grained GitHub token scoped only to `hemanthkavula/AI-Job-Search-Agent` with Actions: Read and write.

Never commit the token to this repository.

## Deploy
`npx wrangler secret put GITHUB_DISPATCH_TOKEN`
`npx wrangler deploy`
