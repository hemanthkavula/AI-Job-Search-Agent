from __future__ import annotations
from docx import Document
from app.resume_generator import jd_keywords,unsupported_jd_terms
def document_text(path):
    d=Document(path);return "\n".join(p.text for p in d.paragraphs)
def ats_audit(job,profile,resume_path):
    text=document_text(resume_path);low=text.lower();verified=jd_keywords(job.description,profile)
    present=[k for k in verified if k.lower() in low];missing=[k for k in verified if k.lower() not in low]
    coverage=round(100*len(present)/max(1,len(verified)))
    unsupported=unsupported_jd_terms(job.description,profile)
    meaningful=sum(any(ch.isdigit() for ch in p.text) for p in Document(resume_path).paragraphs)
    passed=coverage>=90 and not missing and meaningful>=5
    return {"passed":passed,"keyword_coverage":coverage,"verified_jd_keywords":verified,"missing_supported_keywords":missing,"unsupported_jd_terms":unsupported,"metric_bearing_lines":meaningful,"rules":{"min_keyword_coverage":90,"no_missing_supported_keywords":True,"min_metric_bearing_lines":5,"no_fabricated_keywords":True}}
