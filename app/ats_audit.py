from __future__ import annotations
import re
from docx import Document
from app.resume_generator import jd_keywords,unsupported_jd_terms,inferable_terms

ATS_TARGET=95

def document_text(path):
    d=Document(path);return "\n".join(p.text for p in d.paragraphs)

def _norm(s):return re.sub(r"\s+"," ",(s or "").lower())

def ats_audit(job,profile,resume_path):
    text=document_text(resume_path);low=_norm(text);jd=_norm(job.description)
    verified=jd_keywords(job.description,profile);inferred=inferable_terms(job.description)
    supported=list(dict.fromkeys(verified+inferred))
    present=[k for k in supported if _norm(k) in low]
    missing=[k for k in supported if _norm(k) not in low]
    keyword_coverage=100*len(present)/max(1,len(supported))

    title_tokens=[x for x in re.findall(r"[a-z]+",_norm(job.title)) if x not in {"senior","lead","ii","iii"}]
    title_alignment=100 if all(x in low for x in title_tokens) else 70

    sections={"professional summary","technical skills","professional experience","education"}
    section_score=100*sum(x in low for x in sections)/len(sections)

    paras=Document(resume_path).paragraphs
    bullets=[p.text for p in paras if p.style and "List Bullet" in p.style.name]
    metric_lines=sum(bool(re.search(r"\d|%|million|gb|tb|sub-minute",b.lower())) for b in bullets)
    accomplishment_score=min(100,metric_lines*12.5)

    # Weighted internal compatibility score; this is not an employer ATS score.
    score=round(keyword_coverage*.55+title_alignment*.15+section_score*.10+accomplishment_score*.20)
    unsupported=unsupported_jd_terms(job.description,profile)
    passed=score>=ATS_TARGET and keyword_coverage>=95 and not missing
    return {"passed":passed,"internal_ats_score":score,"target":ATS_TARGET,
      "keyword_coverage":round(keyword_coverage),"title_alignment":round(title_alignment),
      "section_score":round(section_score),"accomplishment_score":round(accomplishment_score),
      "supported_jd_terms":supported,"missing_supported_keywords":missing,
      "unsupported_jd_terms":unsupported,"metric_bearing_bullets":metric_lines,
      "status":"ATS_PASS" if passed else "HOLD_ATS_REVIEW",
      "note":"Internal JD-to-resume compatibility score; not a guaranteed employer ATS score."}
