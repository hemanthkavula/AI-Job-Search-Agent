from __future__ import annotations
import argparse,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.config import load_profile
from app.application_inspector import BLOCKER_RE

ROOT=Path(__file__).resolve().parents[1]

def _norm(s):return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()

def _identity(profile):
    parts=(profile.get("name") or "").split()
    contact=profile.get("contact") or {}
    return {"first_name":parts[0] if parts else "","last_name":parts[-1] if len(parts)>1 else "",
            "full_name":profile.get("name",""),"email":contact.get("email",""),"phone":contact.get("phone",""),
            "linkedin":contact.get("linkedin","")}

def _field_key(label):
    x=_norm(label)
    rules=(("first name","first_name"),("last name","last_name"),("full name","full_name"),("email","email"),
           ("phone","phone"),("mobile","phone"),("linkedin","linkedin"))
    return next((k for token,k in rules if token in x),None)

def _question_answer(label,item):
    x=_norm(label);known=item.get("known_answers") or {}
    if "authorized" in x and ("work" in x or "employment" in x):return known.get("authorized_to_work_us")
    # Combined "now or in the future" questions must be Yes for future H-1B need.
    if ("sponsor" in x or "sponsorship" in x) and ("future" in x or "later" in x):return known.get("requires_future_sponsorship")
    if ("sponsor" in x or "sponsorship" in x) and ("now" in x or "currently" in x):return known.get("requires_sponsorship_now")
    if "sponsor" in x or "sponsorship" in x:return known.get("requires_future_sponsorship")
    return None

def _label(el):
    """Resolve real visible form labels, including modern ATS wrappers."""
    try:
        return el.evaluate("""e => {
          const parts=[];
          const add=v=>{if(v && !parts.includes(v.trim())) parts.push(v.trim())};
          add(e.getAttribute('aria-label')); add(e.getAttribute('placeholder'));
          const ids=(e.getAttribute('aria-labelledby')||'').split(/\\s+/).filter(Boolean);
          ids.forEach(id=>{const n=document.getElementById(id); if(n)add(n.innerText||n.textContent)});
          if(e.id){const l=document.querySelector('label[for="'+CSS.escape(e.id)+'"]');if(l)add(l.innerText||l.textContent)}
          const own=e.closest('label');if(own)add(own.innerText||own.textContent);
          const fs=e.closest('fieldset');if(fs){const lg=fs.querySelector('legend');if(lg)add(lg.innerText||lg.textContent)}
          let p=e.parentElement;
          for(let i=0;p && i<3;i++,p=p.parentElement){
            const l=p.querySelector(':scope > label, :scope > span, :scope > div');
            if(l && l!==e)add(l.innerText||l.textContent);
          }
          add(e.getAttribute('name'));add(e.getAttribute('id'));
          return parts.join(' | ').replace(/\\s+/g,' ').trim();
        }""")
    except Exception:
        return el.get_attribute("aria-label") or el.get_attribute("placeholder") or el.get_attribute("name") or el.get_attribute("id") or ""

def _choose(el,value):
    tag=el.evaluate("(e)=>e.tagName.toLowerCase()");typ=(el.get_attribute("type") or "").lower()
    if tag=="select":
        opts=el.locator("option");wanted=_norm(str(value))
        for i in range(opts.count()):
            o=opts.nth(i);txt=o.inner_text();val=o.get_attribute("value")
            if _norm(txt)==wanted or _norm(txt).startswith(wanted):el.select_option(value=val);return True
        return False
    if typ in ("radio","checkbox"):
        lab=_norm(_label(el)+" "+(el.get_attribute("value") or ""))
        if _norm(str(value)) in lab:el.check();return True
        return False
    el.fill(str(value));return True

def _resolve_resume(value):
    if not value:return None
    p=Path(value)
    candidates=[p] if p.is_absolute() else [ROOT/p,p]
    for candidate in candidates:
        try:
            resolved=candidate.resolve()
            if resolved.exists() and resolved.is_file():return resolved
        except Exception:pass
    return None

def autofill(item:dict,headless=True)->dict:
    """Fill deterministic fields and upload the validated PDF. Never submit."""
    profile=load_profile();identity=_identity(profile);url=item.get("url")
    result={"external_id":item.get("external_id"),"url":url,"status":"FILLING","filled":[],"unresolved_required":[],"blockers":[],"submitted":False}
    resume=_resolve_resume(item.get("resume_path"))
    if resume is None:
        return {**result,"status":"MANUAL_ACTION_REQUIRED","reason":"Validated resume file is missing","expected_resume_path":item.get("resume_path")}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=headless);page=browser.new_page()
        try:
            page.goto(url,wait_until="domcontentloaded",timeout=45000)
            body=page.locator("body").inner_text(timeout=10000)
            if BLOCKER_RE.search(body):
                result["blockers"].append("CAPTCHA/MFA/verification challenge detected");result["status"]="MANUAL_ACTION_REQUIRED";return result
            controls=page.locator("input, textarea, select")
            for i in range(min(controls.count(),250)):
                el=controls.nth(i);typ=(el.get_attribute("type") or "").lower();label=_label(el);required=el.get_attribute("required") is not None or el.get_attribute("aria-required")=="true"
                if typ in ("hidden","submit","button"):continue
                if typ=="file":
                    file_label=_norm(label)
                    if any(t in file_label for t in ("resume","cv","curriculum vitae")):
                        try:el.set_input_files(str(resume.resolve()));result["filled"].append({"field":label or "resume","value":"validated PDF"})
                        except Exception:
                            if required:result["unresolved_required"].append(label or "resume upload")
                    elif required:
                        result["unresolved_required"].append(label or "required file upload")
                    continue
                key=_field_key(label);value=identity.get(key) if key else _question_answer(label,item)
                if value not in (None,""):
                    try:
                        if _choose(el,value):result["filled"].append({"field":label,"value":value})
                        elif required:result["unresolved_required"].append(label)
                    except Exception:
                        if required:result["unresolved_required"].append(label)
                elif required:
                    current=""
                    try:current=el.input_value()
                    except Exception:pass
                    if not current:result["unresolved_required"].append(label or f"field_{i}")
            result["unresolved_required"]=sorted(set(result["unresolved_required"]))
            # A page with zero mapped fields is not a successful autofill. Workday
            # commonly lands on a job-description/sign-in step before its application form.
            if not result["filled"]:
                result["status"]="MANUAL_ACTION_REQUIRED"
                result["reason"]="No application form fields were mapped; application form may require an Apply/sign-in step."
            else:
                result["status"]="MANUAL_ACTION_REQUIRED" if result["unresolved_required"] else "AUTOFILLED_REVIEW_REQUIRED"
        except Exception as exc:
            result["status"]="MANUAL_ACTION_REQUIRED";result["reason"]=str(exc)
        finally:browser.close()
    return result

def run(queue_path="generated/application_queue.json",output="generated/application_autofill.json",limit=None,headless=True):
    rows=json.loads(Path(queue_path).read_text(encoding="utf-8"));results=[]
    for item in rows:
        if item.get("status")!="READY_FOR_ATS_ADAPTER":continue
        if limit is not None and len(results)>=limit:break
        results.append(autofill(item,headless))
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(results,indent=2),encoding="utf-8");return results

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--queue",default="generated/application_queue.json");ap.add_argument("--output",default="generated/application_autofill.json");ap.add_argument("--limit",type=int);ap.add_argument("--headed",action="store_true");a=ap.parse_args()
    rows=run(a.queue,a.output,a.limit,not a.headed);print(json.dumps({"processed":len(rows),"autofilled_review_required":sum(x["status"]=="AUTOFILLED_REVIEW_REQUIRED" for x in rows),"manual_action":sum(x["status"]=="MANUAL_ACTION_REQUIRED" for x in rows),"output":a.output},indent=2))
