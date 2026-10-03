# Application Browser Runtime

The production workflow installs Browser Use only when a ready application exists. Browser Use is pinned separately from core dependencies and launches a local headless browser with the existing OpenAI key. No Browser Use Cloud key is required by this implementation.

CAPTCHA/MFA/verification challenges are treated as manual-action blockers; the executor is instructed not to bypass them.
