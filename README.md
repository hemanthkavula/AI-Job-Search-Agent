# AI Job Search Agent

AI-assisted job-search workflow for discovering, scoring, tailoring, reviewing, and tracking Data Engineering applications.

## V1 workflow
1. Ingest a job description.
2. Apply hard filters for target role and employment type.
3. Score the role against the candidate profile.
4. Generate a truthful tailoring plan.
5. Queue the application for human review.
6. Track status in SQLite.

Final submission is intentionally review-gated. Browser/ATS adapters can be added after the core workflow is validated.

## Target roles
- Data Engineer
- Senior Data Engineer
- AWS Data Engineer
- Azure Data Engineer
- Cloud Data Engineer
- Data Platform Engineer
- Lead Data Engineer

## Quick start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## Example
POST `/jobs/analyze` with:
```json
{
  "company": "Example Corp",
  "title": "Senior AWS Data Engineer",
  "location": "New Jersey",
  "employment_type": "Full-Time",
  "description": "Python SQL PySpark AWS Glue S3 Redshift Kafka Terraform..."
}
```

## Safety / accuracy
The agent never invents skills, employers, dates, certifications, degrees, or metrics. Work-authorization, sponsorship, salary, relocation, demographic/EEO, legal attestations, and final submission remain review-gated.
