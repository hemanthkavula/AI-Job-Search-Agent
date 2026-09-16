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

    # Resume quality checks beyond keyword stuffing.
    counts={}
    current=None
    for p in paras:
        t=p.text.strip()
        if t.startswith("Fidelity Investments"): current="Fidelity Investments";counts[current]=0
        elif t.startswith("Cigna Healthcare"): current="Cigna Healthcare";counts[current]=0
        elif t.startswith("Target Corporation"): current="Target Corporation";counts[current]=0
        elif current and p.style and "List Bullet" in p.style.name: counts[current]+=1
    bullet_count_score=100 if counts=={"Fidelity Investments":8,"Cigna Healthcare":7,"Target Corporation":6} else 60
    bad_category=("cloud platforms (aws):" in low and "bigquery" in low.split("cloud platforms (aws):",1)[1].split("\n",1)[0])
    taxonomy_score=60 if bad_category else 100
    # Weighted internal compatibility score; not an employer ATS score.
    score=round(keyword_coverage*.45+title_alignment*.10+section_score*.10+accomplishment_score*.15+bullet_count_score*.10+taxonomy_score*.10)
    unsupported=unsupported_jd_terms(job.description,profile)
    # Do not confuse keyword completeness with resume quality. Require a strong
    # discovery match as well as full supported-keyword coverage.
    discovery_score=getattr(job,"discovery_score",None)
    quality_gate=(discovery_score is None or discovery_score>=80)
    passed=score>=ATS_TARGET and keyword_coverage>=95 and not missing and quality_gate
    return {"passed":passed,"internal_ats_score":score,"target":ATS_TARGET,
      "keyword_coverage":round(keyword_coverage),"title_alignment":round(title_alignment),
      "section_score":round(section_score),"accomplishment_score":round(accomplishment_score),
      "supported_jd_terms":supported,"missing_supported_keywords":missing,
      "unsupported_jd_terms":unsupported,"metric_bearing_bullets":metric_lines,"bullet_counts":counts,"bullet_count_score":bullet_count_score,"skills_taxonomy_score":taxonomy_score,"discovery_score":discovery_score,"quality_gate_passed":quality_gate,
      "status":"ATS_PASS" if passed else "HOLD_ATS_REVIEW",
      "note":"Internal JD-to-resume compatibility score; not a guaranteed employer ATS score."}
