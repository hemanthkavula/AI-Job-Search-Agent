from __future__ import annotations
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,re,shutil,zipfile
from lxml import etree
from docx import Document
from docx.oxml.ns import qn
from app.master_resume import load_master_resume
from app.resume_generator import ROOT,clean_company_name,safe_name

WORD_FORMAT_PATH=ROOT/"data"/"master_word_format.json"
WORD_TEMPLATE_PATH=ROOT/"data"/"Hemanth_Kavula_Senior_Data_Engineer_Resume.docx"
W_URI="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W=f"{{{W_URI}}}"
XMLSPACE="{http://www.w3.org/XML/1998/namespace}space"
NS={"w":W_URI}


def load_word_format(path=WORD_FORMAT_PATH):
    d=json.loads(path.read_text(encoding="utf-8"));s=d.get("source") or {}
    if s.get("authority")!="user_uploaded_word_format_template":raise RuntimeError("Word format record is not user-authoritative")
    if s.get("technical_content_authority") is not False:raise RuntimeError("Word template cannot be technical-content authority")
    return d

def _sha(path):
    h=hashlib.sha256();h.update(path.read_bytes());return h.hexdigest()
def _template(fmt=None):
    fmt=fmt or load_word_format(); exp=fmt["source"].get("sha256")
    if not WORD_TEMPLATE_PATH.exists():raise RuntimeError(f"Authoritative Word template missing: {WORD_TEMPLATE_PATH}")
    got=_sha(WORD_TEMPLATE_PATH)
    if exp and got!=exp:raise RuntimeError(f"Word template checksum mismatch: expected {exp}, got {got}")
    return WORD_TEMPLATE_PATH

def canonical_resume_title(title):
    raw=re.sub(r"\s+"," ",str(title or "")).strip();m=re.search(r"(?i)\b(?:(principal|staff|lead|senior|sr\.?|junior|jr\.?)\s+)?data\s+engineer(?:ing)?\b",raw)
    if m:
        lvl=(m.group(1) or "").lower().rstrip(".");lvl={"sr":"Senior","jr":"Junior"}.get(lvl,lvl.title());core="Data Engineering" if "engineering" in m.group(0).lower() else "Data Engineer";return f"{lvl} {core}".strip()
    raw=re.sub(r"(?i)^\s*(?:immediate interviews?|urgent(?: hiring)?|hiring now)\s*[-:|]\s*","",raw)
    raw=re.split(r"\s+(?:[-|/]\s*)(?=(?:airflow|dbt|kubernetes|openshift|aws|azure|gcp|snowflake|databricks|hybrid|remote|onsite|on-site)\b)",raw,1,flags=re.I)[0]
    return raw.strip(" -|:/") or "Senior Data Engineer"
def _summary_parts(text):
    text=str(text or "").strip();p=[x.strip() for x in re.split(r"\n\s*\n",text) if x.strip()]
    if len(p)>=2:return p[:2]
    s=[x.strip() for x in re.split(r"(?<=[.!?])\s+",text) if x.strip()]
    if len(s)>=4:
        i=max(1,len(s)//2);return [" ".join(s[:i])," ".join(s[i:])]
    if len(s)==3:return [s[0]," ".join(s[1:])]
    if len(s)==2:return s
    return [text] if text else []
def _terms(g):
    out=[]
    for vals in (g.get("skills") or {}).values():
        for v in vals or []:
            v=str(v).strip()
            if v and v.casefold() not in {x.casefold() for x in out}:out.append(v)
    return sorted(out,key=len,reverse=True)
def _emphasis(text,g,n):
    out=[]
    for t in _terms(g):
        if len(t)>=3 and re.search(r"(?<![A-Za-z0-9])"+re.escape(t)+r"(?![A-Za-z0-9])",text,re.I):out.append(t)
        if len(out)>=n:break
    if not out:
        w=re.findall(r"\S+",text);start=1 if w and w[0].rstrip(".,:;").lower() in {"built","developed","designed","implemented","modeled","architected","automated","enabled","optimized","established","supported","created","engineered","delivered","owned","maintained"} else 0
        if w:out=[" ".join(w[start:start+5]).strip(" ,.;:")]
    return out[:n]

def _pt(root):return root.xpath(".//w:body/w:p",namespaces=NS)
def _text(p):return "".join(p.xpath(".//w:t/text()",namespaces=NS)).strip()
def _between(ps,a,b):
    ia=next(i for i,p in enumerate(ps) if _text(p).upper()==a);ib=next(i for i,p in enumerate(ps) if i>ia and _text(p).upper()==b);return ps[ia+1:ib]
def _rpr(p,bold):
    for r in p.xpath(".//w:r",namespaces=NS):
        if not r.xpath("./w:t",namespaces=NS):continue
        has=bool(r.xpath("./w:rPr/w:b|./w:rPr/w:bCs",namespaces=NS))
        if has==bold:
            x=r.find(W+"rPr");return deepcopy(x) if x is not None else None
    return None
def _clear(p):
    for c in list(p):
        if c.tag!=W+"pPr":p.remove(c)
def _run(p,s,rpr=None):
    r=etree.SubElement(p,W+"r")
    if rpr is not None:r.append(deepcopy(rpr))
    t=etree.SubElement(r,W+"t");t.text=s
    if s[:1].isspace() or s[-1:].isspace():t.set(XMLSPACE,"preserve")
def _replace(p,text,phrases,normal,bold):
    _clear(p);phrases=sorted(dict.fromkeys([x for x in phrases if x]),key=len,reverse=True)
    if not phrases:return _run(p,text,normal)
    pat=re.compile("("+"|".join(re.escape(x) for x in phrases)+")",re.I);lookup={x.casefold() for x in phrases}
    for part in pat.split(text):
        if part:_run(p,part,bold if part.casefold() in lookup else normal)
def _exp(ps):
    master=load_master_resume();out={}
    for row in master["experience"]:
        c=row["company"];hi=next(i for i,p in enumerate(ps) if _text(p).startswith(c));ri=next(i for i in range(hi+1,len(ps)) if _text(ps[i])=="Roles & Responsibilities:");bul=[];env=None
        for p in ps[ri+1:]:
            tx=_text(p)
            if tx.startswith("Environment:"):env=p;break
            if tx:bul.append(p)
        if len(bul)!=len(row["bullets"]) or env is None:raise RuntimeError(f"Word template experience structure mismatch for {c}")
        out[c]={"bullets":bul,"environment":env}
    return out
def _write_docx(template,out,xml):
    with zipfile.ZipFile(template,"r") as zin,zipfile.ZipFile(out,"w") as zout:
        for info in zin.infolist():zout.writestr(info,xml if info.filename=="word/document.xml" else zin.read(info.filename))
def _same_non_document_parts(a,b):
    with zipfile.ZipFile(a) as za,zipfile.ZipFile(b) as zb:
        na={x.filename for x in za.infolist()};nb={x.filename for x in zb.infolist()}
        if na!=nb:return False
        return all(za.read(n)==zb.read(n) for n in na if n!="word/document.xml")
def _no_page_breaks(root):
    return not root.xpath(".//w:pageBreakBefore|.//w:br[@w:type='page']",namespaces=NS)
def _ppr(p):
    x=p.find(W+"pPr");return b"" if x is None else etree.tostring(x)
def _xml(path):
    with zipfile.ZipFile(path) as z:return etree.fromstring(z.read("word/document.xml"))
def validate_master_format_contract(path,master=None,word_format=None):
    master=master or load_master_resume();fmt=word_format or load_word_format();tpl=_template(fmt);reasons=[]
    if not _same_non_document_parts(tpl,path):reasons.append("non_document_word_package_changed")
    src=_xml(tpl);out=_xml(path);sp=_pt(src);op=_pt(out)
    if etree.tostring(src.find(".//"+W+"sectPr"))!=etree.tostring(out.find(".//"+W+"sectPr")):reasons.append("section_properties_changed")
    if not _no_page_breaks(out):reasons.append("forced_page_break")
    for h in ("PROFESSIONAL SUMMARY","TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE","EDUCATION"):
        a=next((p for p in sp if _text(p).upper()==h),None);b=next((p for p in op if _text(p).upper()==h),None)
        if a is None or b is None:reasons.append("heading_"+h)
        elif etree.tostring(a)!=etree.tostring(b):reasons.append("heading_format_"+h)
    bud=fmt["content_budget"]
    sm=[p for p in _between(op,"PROFESSIONAL SUMMARY","TECHNICAL SKILLS") if _text(p)]
    if len(sm)!=2 or sum(len(_text(p)) for p in sm)>int(bud["summary_total_max_chars"]):reasons.append("summary_budget")
    sk=[p for p in _between(op,"TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE") if _text(p)]
    if not sk or len(sk)>int(bud["skills_max_rows"]) or sum(len(_text(p)) for p in sk)>int(bud["skills_total_max_chars"]):reasons.append("skills_budget")
    sx=[p for p in _between(sp,"PROFESSIONAL SUMMARY","TECHNICAL SKILLS") if _text(p)];kx=[p for p in _between(sp,"TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE") if _text(p)]
    if sx and any(_ppr(p)!=_ppr(sx[0]) for p in sm):reasons.append("summary_paragraph_format")
    if kx and any(_ppr(p)!=_ppr(kx[0]) for p in sk):reasons.append("skills_paragraph_format")
    lo=_exp(op);ls=_exp(sp)
    for row in master["experience"]:
        c=row["company"]
        if len(lo[c]["bullets"])!=len(row["bullets"]):reasons.append(c+"_bullet_count")
        if any(_ppr(p)!=_ppr(ls[c]["bullets"][0]) for p in lo[c]["bullets"]):reasons.append(c+"_bullet_format")
        if _ppr(lo[c]["environment"])!=_ppr(ls[c]["environment"]):reasons.append(c+"_environment_format")
    return {"passed":not reasons,"reasons":list(dict.fromkeys(reasons)),"format_authority":"user_uploaded_word_format_template","format_source":"live_user_uploaded_docx_template","word_template_sha256":fmt["source"].get("sha256")}
def _out(job,d):
    root=ROOT/d;root.mkdir(parents=True,exist_ok=True);co=clean_company_name(job.company);ti=canonical_resume_title(job.title);stem=f"Hemanth_Kavula_{safe_name(co)}_{safe_name(ti)}";ts=datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S");folder=root/f"{safe_name(co)}_{safe_name(ti)}_{ts}";folder.mkdir(parents=True,exist_ok=True);return folder/f"{stem}.docx"
def render_llm_resume(job,profile,generated,output_dir="generated/resumes"):
    fmt=load_word_format();tpl=_template(fmt);out=_out(job,output_dir)
    if generated.get("_master_mode"):shutil.copy2(tpl,out);return str(out)
    bud=fmt["content_budget"];master=load_master_resume()
    with zipfile.ZipFile(tpl) as z:root=etree.fromstring(z.read("word/document.xml"))
    ps=_pt(root)
    hp=ps[1];normal=_rpr(hp,False);_clear(hp);_run(hp,canonical_resume_title(job.title),normal)
    sps=[p for p in _between(ps,"PROFESSIONAL SUMMARY","TECHNICAL SKILLS") if _text(p)];parts=_summary_parts(generated.get("summary",""))
    if len(parts)!=2 or sum(len(x) for x in parts)>int(bud["summary_total_max_chars"]):raise RuntimeError("Generated summary violates Word template budget")
    sn=_rpr(sps[0],False) or _rpr(sps[1],False);sb=_rpr(sps[0],True) or _rpr(sps[1],True)
    for p,t in zip(sps,parts):_replace(p,t,_emphasis(t,generated,5),sn,sb)
    ps=_pt(root);sks=[p for p in _between(ps,"TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE") if _text(p)];items=list((generated.get("skills") or {}).items())
    if not items or len(items)>int(bud["skills_max_rows"]):raise RuntimeError("Generated Technical Skills violate Word template row budget")
    rendered=[f"{k}: {', '.join(str(v) for v in (vals or []))}" for k,vals in items]
    if sum(len(x) for x in rendered)>int(bud["skills_total_max_chars"]):raise RuntimeError("Generated Technical Skills violate Word template character budget")
    kb=_rpr(sks[0],True);kn=_rpr(sks[0],False)
    for p,(k,vals) in zip(sks,items):_clear(p);_run(p,str(k),kb);_run(p,": ",kn);_run(p,", ".join(str(v) for v in vals or []),kn)
    body=root.find(".//"+W+"body")
    for p in sks[len(items):]:body.remove(p)
    ps=_pt(root);layout=_exp(ps);srcroot=_xml(tpl);sl=_exp(_pt(srcroot));allb=[p for x in sl.values() for p in x["bullets"]];bn=next((_rpr(p,False) for p in allb if _rpr(p,False) is not None),None);bb=next((_rpr(p,True) for p in allb if _rpr(p,True) is not None),None);envs=[x["environment"] for x in sl.values()];eb=next((_rpr(p,True) for p in envs if _rpr(p,True) is not None),None);en=next((_rpr(p,False) for p in envs if _rpr(p,False) is not None),None)
    by={x.get("company"):x for x in generated.get("experience") or []}
    for row in master["experience"]:
        c=row["company"];item=by.get(c)
        if not item:raise RuntimeError(f"Generated experience missing {c}")
        bullets=[str(x).strip() for x in item.get("bullets") or []]
        if len(bullets)!=len(row["bullets"]):raise RuntimeError(f"{c} must contain exactly {len(row['bullets'])} bullets")
        if any(len(re.findall(r"\S+",x))>int(bud["bullet_max_words"]) for x in bullets):raise RuntimeError(f"{c} bullet exceeds Word template budget")
        for p,t in zip(layout[c]["bullets"],bullets):_replace(p,t,_emphasis(t,generated,2),bn,bb)
        e=str(item.get("environment") or "").strip()
        if not e or len(e)>int(bud["environment_max_chars"]):raise RuntimeError(f"{c} Environment violates Word template budget")
        p=layout[c]["environment"];_clear(p);_run(p,"Environment",eb);_run(p,": "+e,en)
    xml=etree.tostring(root,xml_declaration=True,encoding="UTF-8",standalone="yes");_write_docx(tpl,out,xml)
    check=validate_master_format_contract(out,master,fmt)
    if not check["passed"]:raise RuntimeError("Generated resume violated live Word-template format contract: "+"; ".join(check["reasons"]))
    return str(out)