from __future__ import annotations
import re
from collections import Counter
from docx import Document
from app.resume_generator import jd_keywords,unsupported_jd_terms,inferable_terms

ATS_TARGET=95
EXPECTED_COUNTS={"Fidelity Investments":8,"Cigna Healthcare":7,"Target Corporation":6}
METRIC_LIMITS={"Fidelity Investments":2,"Cigna Healthcare":2,"Target Corporation":0}

TECH_NUMBER_PATTERNS=[r"\bs3\b",r"\bec2\b",r"\bscd\s*(?:type\s*)?2\b",r"\bgen\s*2\b",r"\badls\s*gen2\b",r"\bpython\s*3\b"]

def document_text(path):
    d=Document(path);return "\n".join(p.text for p in d.paragraphs)

def _norm(s):return re.sub(r"\s+"," ",(s or "").lower()).strip()

def _is_metric_bullet(text):
    """Count business/scale/result metrics, not digits embedded in technology names."""
    s=_norm(text)
    for pat in TECH_NUMBER_PATTERNS:s=re.sub(pat," ",s,flags=re.I)
    patterns=[
      r"\b\d+(?:\.\d+)?\s*%",
      r"\b\d+(?:\.\d+)?\s*(?:k|m|b|million|billion)\b",
      r"\b\d+(?:\.\d+)?\s*(?:gb|tb|pb|mb)\b",
      r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?)\b",
      r"\b\d+(?:\.\d+)?\+?\s*(?:events?|records?|rows?|transactions?|members?|pipelines?|tables?|datasets?|jobs?|rules?)\b",
      r"\b(?:reduced|improved|increased|decreased|cut|lowered|accelerated|saved)\b[^.;]{0,45}\b\d+(?:\.\d+)?\b"
    ]
    return any(re.search(p,s,re.I) for p in patterns)

def _experience_bullets(paras):
    by_company={k:[] for k in EXPECTED_COUNTS};current=None
    for p in paras:
        t=p.text.strip()
        if t.startswith("Fidelity Investments"):current="Fidelity Investments"
        elif t.startswith("Cigna Healthcare"):current="Cigna Healthcare"
        elif t.startswith("Target Corporation"):current="Target Corporation"
        elif current and p.style and "List Bullet" in p.style.name:by_company[current].append(t)
    return by_company

def _repetition_findings(bullets):
    """Flag repeated 4+ word phrases and excessive identical opening verbs."""
    normalized=[re.findall(r"[a-z0-9+#.-]+",_norm(x)) for x in bullets]
    phrases=Counter()
    for words in normalized:
        seen=set()
        for n in (4,5,6):
            for i in range(max(0,len(words)-n+1)):
                phrase=" ".join(words[i:i+n])
                if phrase not in seen:phrases[phrase]+=1;seen.add(phrase)
    repeated=[p for p,c in phrases.items() if c>=3]
    openings=Counter(words[0] for words in normalized if words)
    repeated_openings={k:v for k,v in openings.items() if v>=5}
    return repeated[:10],repeated_openings

def _unsupported_claims(by_company,unsupported):
    findings=[]
    for company,bullets in by_company.items():
        for bullet in bullets:
            low=_norm(bullet)
            for term in unsupported:
                if re.search(r"(?<![a-z0-9])"+re.escape(term.lower())+r"(?![a-z0-9])",low):
                    findings.append({"company":company,"term":term,"bullet":bullet})
    return findings

def ats_audit(job,profile,resume_path):
    text=document_text(resume_path);low=_norm(text)
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
    by_company=_experience_bullets(paras)
    bullets=[b for xs in by_company.values() for b in xs]
    counts={k:len(v) for k,v in by_company.items()}
    bullet_count_score=100 if counts==EXPECTED_COUNTS else 60

    metric_counts={company:sum(_is_metric_bullet(b) for b in xs) for company,xs in by_company.items()}
    metric_lines=sum(metric_counts.values())
    metric_violations={c:{"count":metric_counts[c],"limit":limit} for c,limit in METRIC_LIMITS.items() if metric_counts[c]>limit}
    # Metrics improve evidence only within the user's truthful employer limits.
    accomplishment_score=min(100,60+min(metric_lines,4)*10)
    if metric_violations:accomplishment_score=max(40,accomplishment_score-20*len(metric_violations))

    bad_category=("cloud platforms (aws):" in low and "bigquery" in low.split("cloud platforms (aws):",1)[1].split("\n",1)[0])
    taxonomy_score=60 if bad_category else 100

    repeated_phrases,repeated_openings=_repetition_findings(bullets)
    repetition_score=100
    if repeated_phrases:repetition_score-=min(35,len(repeated_phrases)*7)
    if repeated_openings:repetition_score-=min(20,sum(v-4 for v in repeated_openings.values())*4)
    repetition_score=max(40,repetition_score)

    unsupported=unsupported_jd_terms(job.description,profile)
    unsupported_claims=_unsupported_claims(by_company,unsupported)
    truthfulness_score=100 if not unsupported_claims else max(0,100-25*len(unsupported_claims))

    # Compatibility and quality are separate. High keyword coverage cannot override
    # repetition, unsupported employer claims, metric-rule violations, or structure.
    compatibility_score=round(keyword_coverage*.55+title_alignment*.15+section_score*.10+bullet_count_score*.10+taxonomy_score*.10)
    quality_score=round(accomplishment_score*.30+repetition_score*.30+truthfulness_score*.30+bullet_count_score*.10)
    score=round(compatibility_score*.65+quality_score*.35)

    discovery_score=getattr(job,"discovery_score",None)
    discovery_gate=(discovery_score is None or discovery_score>=80)
    structural_gate=counts==EXPECTED_COUNTS
    metric_gate=not metric_violations
    repetition_gate=repetition_score>=85
    truthfulness_gate=not unsupported_claims
    quality_gate=discovery_gate and structural_gate and metric_gate and repetition_gate and truthfulness_gate
    passed=score>=ATS_TARGET and keyword_coverage>=95 and not missing and quality_gate

    return {"passed":passed,"internal_ats_score":score,"target":ATS_TARGET,
      "compatibility_score":compatibility_score,"quality_score":quality_score,
      "keyword_coverage":round(keyword_coverage),"title_alignment":round(title_alignment),
      "section_score":round(section_score),"accomplishment_score":round(accomplishment_score),
      "supported_jd_terms":supported,"missing_supported_keywords":missing,
      "unsupported_jd_terms":unsupported,"unsupported_employer_claims":unsupported_claims,
      "truthfulness_score":truthfulness_score,"metric_bearing_bullets":metric_lines,
      "metric_counts_by_employer":metric_counts,"metric_violations":metric_violations,
      "bullet_counts":counts,"bullet_count_score":bullet_count_score,"skills_taxonomy_score":taxonomy_score,
      "repetition_score":repetition_score,"repeated_phrases":repeated_phrases,"repeated_opening_verbs":repeated_openings,
      "discovery_score":discovery_score,"quality_gate_passed":quality_gate,
      "quality_gates":{"discovery":discovery_gate,"structure":structural_gate,"metrics":metric_gate,"repetition":repetition_gate,"truthfulness":truthfulness_gate},
      "status":"ATS_PASS" if passed else "HOLD_ATS_REVIEW",
      "note":"Internal JD-to-resume compatibility and quality score; not a guaranteed employer ATS score."}
