# Live source testing

The repository now includes real public ATS boards in `data/job_sources.json`.

Run:

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m app.daily_runner --sources data/job_sources.json --min-score 70
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/dashboard`.

## Current scope
Discovery uses public Lever/Ashby job-board endpoints. Results still pass through title/employment filters and resume scoring. Do not assume every discovered role is eligible for the candidate; sponsorship, location, clearance, years-of-experience and employer-specific constraints require review.

## Application assistance
For a selected Lever application:

```bash
cp data/application_profile.example.json data/application_profile.json
python -m app.browser.runner --adapter lever --url "APPLICATION_URL" --candidate data/application_profile.json --resume "PATH_TO_GENERATED_DOCX"
```

The browser assistant fills common fields and pauses for human review. It does not click final submit.
