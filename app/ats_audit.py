from __future__ import annotations
import re
from collections import Counter
from docx import Document
from app.resume_generator import jd_keywords,inferable_terms,jd_skill_terms

ATS_TARGET=95
EVIDENCE_TARGET=95
HUMAN_QUALITY_TARGET=90
EXPECTED_COUNTS={"Fidelity Investments":8,"Cigna Healthcare":7,"Target Corporation":6}
METRIC_LIMITS={"Fidelity Investments":2,"Cigna Healthcare":2,"Target Corporation":0}
TECH_NUMBER_PATTERNS=[r"\bs3\b",r"\bec2\b",r"\bscd\s*(?:type\s*)?2\b",r"\bgen\s*2\b",r"\badls\s*gen2\b",r"\bpython\s*3\b"]

def document_text(path):
    d=Document(path);return "\n".join(p.text for p in d.paragraphs)
def _norm(s):return re.sub(r"\s+"," ",(s or "").lower()).strip()
def _contains(text,term):
    return bool(re.search(r"(?<![a-z0-9])"+re.escape(_norm(term))+r"(?![a-z0-9])",_norm(text)))
def _is_metric_bullet(text):
    s=_norm(text)
    for pat in TECH_NUMBER_PATTERNS:s=re.sub(pat," ",s,flags=re.I)
    patterns=[r"\b\d+(?:\.\d+)?\s*%",r"\b\d+(?:\.\d+)?\s*(?:k|m|b|million|billion)\b",r"\b\d+(?:\.\d+)?\s*(?:gb|tb|pb|mb)\b",r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?)\b",r"\b\d+(?:\.\d+)?\+?\s*(?:events?|records?|rows?|transactions?|members?|pipelines?|tables?|datasets?|jobs?|rules?)\b",r"\b(?:reduced|improved|increased|decreased|cut|lowered|accelerated|saved)\b[^.;]{0,45}\b\d+(?:\.\d+)?\b"]
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
    normalized=[re.findall(r"[a-z0-9+#.-]+",_norm(x)) for x in bullets];phrases=Counter()
    for words in normalized:
        seen=set()
        for n in (4,5,6):
            for i in range(max(0,len(words)-n+1)):
                phrase=" ".join(words[i:i+n])
                if phrase not in seen:phrases[phrase]+=1;seen.add(phrase)
    repeated=[p for p,c in phrases.items() if c>=3];openings=Counter(words[0] for words in normalized if words)
    return repeated[:10],{k:v for k,v in openings.items() if v>=5}
def _technical_skills_text(paras):
    collecting=False;rows=[]
    for p in paras:
        t=p.text.strip()
        if t.upper()=="TECHNICAL SKILLS":collecting=True;continue
        if collecting and t.upper()=="PROFESSIONAL EXPERIENCE":break
        if collecting and t:rows.append(t)
    return "\n".join(rows)
def _evidence_coverage(jd_terms,skills_text,bullets):
    experience_text="\n".join(bullets)
    listed=[t for t in jd_terms if _contains(skills_text,t)]
    evidenced=[t for t in listed if _contains(experience_text,t)]
    gaps=[t for t in listed if t not in evidenced]
    score=100*len(evidenced)/max(1,len(listed))
    return listed,evidenced,gaps,round(score)
def _readability_score(bullets,repetition_score):
    if not bullets:return 0
    lengths=[len(re.findall(r"\b\w+[+#.-]*\b",b)) for b in bullets]
    long_count=sum(n>38 for n in lengths);very_long=sum(n>50 for n in lengths)
    avg=sum(lengths)/len(lengths)
    score=100-min(25,long_count*3)-min(20,very_long*5)
    if avg>34:score-=10
    score=min(score,repetition_score)
    return max(40,round(score))

def ats_audit(job,profile,resume_path):
    text=document_text(resume_path);low=_norm(text)
    verified=jd_keywords(job.description,profile);inferred=inferable_terms(job.description);jd_terms=jd_skill_terms(job.description)
    targeted=list(dict.fromkeys(verified+inferred+jd_terms))
    present=[k for k in targeted if _contains(low,k)];missing=[k for k in targeted if not _contains(low,k)]
    keyword_coverage=100*len(present)/max(1,len(targeted))
    title_tokens=[x for x in re.findall(r"[a-z]+",_norm(job.title)) if x not in {"senior","lead","ii","iii"}];title_alignment=100 if all(x in low for x in title_tokens) else 70
    sections={"professional summary","technical skills","professional experience","education"};section_score=100*sum(x in low for x in sections)/len(sections)
    paras=Document(resume_path).paragraphs;by_company=_experience_bullets(paras);bullets=[b for xs in by_company.values() for b in xs]
    counts={k:len(v) for k,v in by_company.items()};bullet_count_score=100 if counts==EXPECTED_COUNTS else 60
    metric_counts={c:sum(_is_metric_bullet(b) for b in xs) for c,xs in by_company.items()};metric_lines=sum(metric_counts.values());metric_violations={c:{"count":metric_counts[c],"limit":limit} for c,limit in METRIC_LIMITS.items() if metric_counts[c]>limit}
    accomplishment_score=min(100,60+min(metric_lines,4)*10)
    if metric_violations:accomplishment_score=max(40,accomplishment_score-20*len(metric_violations))
    repeated_phrases,repeated_openings=_repetition_findings(bullets);repetition_score=100
    if repeated_phrases:repetition_score-=min(35,len(repeated_phrases)*7)
    if repeated_openings:repetition_score-=min(20,sum(v-4 for v in repeated_openings.values())*4)
    repetition_score=max(40,repetition_score)
    skills_text=_technical_skills_text(paras);listed,evidenced,evidence_gaps,evidence_score=_evidence_coverage(jd_terms,skills_text,bullets)
    readability_score=_readability_score(bullets,repetition_score)
    taxonomy_score=100
    human_quality_score=round(readability_score*.40+repetition_score*.25+accomplishment_score*.20+bullet_count_score*.15)
    compatibility_score=round(keyword_coverage*.60+title_alignment*.15+section_score*.10+bullet_count_score*.10+taxonomy_score*.05)
    score=round(compatibility_score*.70+human_quality_score*.30)
    discovery_score=getattr(job,"discovery_score",None);discovery_gate=(discovery_score is None or discovery_score>=80);structural_gate=counts==EXPECTED_COUNTS;metric_gate=not metric_violations;repetition_gate=repetition_score>=85;evidence_gate=evidence_score>=EVIDENCE_TARGET and not evidence_gaps;human_gate=human_quality_score>=HUMAN_QUALITY_TARGET
    quality_gate=discovery_gate and structural_gate and metric_gate and repetition_gate and evidence_gate and human_gate
    passed=score>=ATS_TARGET and keyword_coverage>=95 and not missing and quality_gate
    return {"passed":passed,"internal_ats_score":score,"target":ATS_TARGET,"compatibility_score":compatibility_score,"human_quality_score":human_quality_score,"human_quality_target":HUMAN_QUALITY_TARGET,"readability_score":readability_score,"keyword_coverage":round(keyword_coverage),"title_alignment":round(title_alignment),"section_score":round(section_score),"accomplishment_score":round(accomplishment_score),"targeted_jd_terms":targeted,"missing_jd_keywords":missing,"technical_skills_jd_terms":listed,"experience_evidenced_jd_terms":evidenced,"skills_without_experience_evidence":evidence_gaps,"technology_evidence_coverage":evidence_score,"technology_evidence_target":EVIDENCE_TARGET,"metric_bearing_bullets":metric_lines,"metric_counts_by_employer":metric_counts,"metric_violations":metric_violations,"bullet_counts":counts,"bullet_count_score":bullet_count_score,"skills_taxonomy_score":taxonomy_score,"repetition_score":repetition_score,"repeated_phrases":repeated_phrases,"repeated_opening_verbs":repeated_openings,"discovery_score":discovery_score,"quality_gate_passed":quality_gate,"quality_gates":{"discovery":discovery_gate,"structure":structural_gate,"metrics":metric_gate,"repetition":repetition_gate,"technology_evidence":evidence_gate,"human_quality":human_gate},"status":"ATS_PASS" if passed else "HOLD_ATS_REVIEW","note":"Internal ATS/quality estimate only; release requires JD keyword alignment, experience evidence for JD technologies listed in skills, and human-readability gates."}
