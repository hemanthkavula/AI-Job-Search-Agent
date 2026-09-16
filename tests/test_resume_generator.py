from types import SimpleNamespace
from pathlib import Path
from app.resume_generator import generate_resume

def test_resume_generation(tmp_path):
    profile={
      "name":"Hemanth Kavula","headline":"Senior Data Engineer",
      "skills":["Python","SQL","AWS Glue"],
      "education":[{"degree":"Master of Science in Computer Science","school":"Rowan University","location":"Glassboro, NJ","start":"Jan 2024","end":"Dec 2025"}],
      "experience":[{"company":"Example","title":"Data Engineer","dates":"2025 – Present","evidence":["Built Python and AWS Glue pipelines"]}]
    }
    job=SimpleNamespace(company="Test Co",title="AWS Data Engineer",description="Python AWS Glue")
    analysis={"matched_skills":["Python","AWS Glue"]}
    path=generate_resume(job,analysis,profile,output_dir=str(tmp_path))
    assert Path(path).exists()
