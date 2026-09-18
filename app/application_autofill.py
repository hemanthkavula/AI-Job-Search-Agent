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
    raw_phone=contact.get("phone","")
    digits=re.sub(r"\\D+","",raw_phone)
    us_phone=digits[-10:] if len(digits)>=10 else digits
    return {"first_name":parts[0] if parts else "","last_name":parts[-1] if len(parts)>1 else "",
            "full_name":profile.get("name",""),"email":contact.get("email",""),"phone":us_phone,
            "linkedin":contact.get("linkedin","")}

def _field_key(label):
    x=_norm(label)
    if "phone extension" in x or x.endswith(" extension") or "country phone code" in x:return None
    rules=(("first name","first_name"),("last name","last_name"),("full name","full_name"),("email","email"),
           ("phone number","phone"),("mobile","phone"),("linkedin","linkedin"))
    return next((k for token,k in rules if token in x),None)

def _question_answer(label,item):
    x=_norm(label);known=item.get("known_answers") or {}
    if "how did you hear about us" in x:return known.get("source") or "Company Website"
    if "employed by adobe in the past" in x:return known.get("previously_employed_by_company") or "No"
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


def _workday_select_dropdown(page,el,value):
    """Select a Workday prompt value and verify the option is committed."""
    wanted=str(value)
    try:
        # Workday prompt inputs usually live inside a prompt/search wrapper.
        wrapper=el.locator("xpath=ancestor::*[@data-automation-id='formField'][1]")
        if not wrapper.count():wrapper=el.locator("xpath=ancestor::*[self::div or self::fieldset][1]")
        trigger=None
        for sel in ('button[data-automation-id="promptIcon"]','button[aria-haspopup="listbox"]',
                    '[role="combobox"]','input'):
            loc=wrapper.locator(sel).first if wrapper.count() else page.locator(sel).first
            if loc.count() and loc.is_visible():trigger=loc;break
        if trigger is None:trigger=el
        trigger.click(timeout=3000)
        page.wait_for_timeout(600)
        # If the prompt exposes a searchable input, type only to filter; selection
        # is complete only after clicking an actual option.
        try:
            if el.is_editable():el.fill(wanted)
        except Exception:pass
        page.wait_for_timeout(700)
        options=page.locator('[role="option"], [data-automation-id="promptOption"], [data-automation-id="promptOptionText"]')
        for i in range(min(options.count(),100)):
            opt=options.nth(i)
            try:
                txt=_norm(opt.inner_text())
                if _norm(wanted) in txt and opt.is_visible():
                    opt.click(timeout=3000);page.wait_for_timeout(500)
                    # Verify Workday no longer reports zero selected for this field.
                    text=_norm(wrapper.inner_text()) if wrapper.count() else ""
                    if "0 items selected" not in text:return True
            except Exception:pass
        # Keyboard fallback still requires verifying a committed selection.
        try:
            el.press("ArrowDown");el.press("Enter");page.wait_for_timeout(400)
            text=_norm(wrapper.inner_text()) if wrapper.count() else ""
            return "0 items selected" not in text
        except Exception:return False
    except Exception:return False

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
    if el.get_attribute("role")=="combobox":
        try:
            el.click();el.fill(str(value));el.press("ArrowDown");el.press("Enter");return True
        except Exception:return False
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


def _workday_enter_application(page):
    """Wait for the Workday SPA, enter Apply flow, and return diagnostics."""
    diag={"provider":"workday","url_before":page.url,"title":None,"ready_state":None,
          "apply_selector":None,"manual_selector":None,"url_after_apply":None,
          "url_after_manual":None,"visible_actions":[],"gate":None,
          "body_excerpt":None,"control_count":0}
    try:
        page.wait_for_load_state("domcontentloaded",timeout=15000)
        try: page.wait_for_load_state("networkidle",timeout=10000)
        except Exception: pass
        # Workday is a client-rendered SPA; DOMContentLoaded is often too early.
        page.wait_for_timeout(2500)
        diag["title"]=page.title()
        diag["ready_state"]=page.evaluate("document.readyState")
        diag["control_count"]=page.locator("button, a, input, textarea, select").count()
        apply_selectors=[
            '[data-automation-id="applyButton"]',
            'button:has-text("Apply Now")','a:has-text("Apply Now")',
            'button:has-text("Apply")','a:has-text("Apply")',
            '[role="button"]:has-text("Apply")'
        ]
        # Give the SPA up to 15 seconds to expose an Apply action.
        deadline=15000
        elapsed=0
        chosen=None
        while elapsed<=deadline and not chosen:
            for sel in apply_selectors:
                try:
                    loc=page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        chosen=(sel,loc);break
                except Exception:pass
            if not chosen:
                page.wait_for_timeout(1000);elapsed+=1000
        if chosen:
            sel,loc=chosen;diag["apply_selector"]=sel
            loc.click(timeout=7000)
            page.wait_for_timeout(2000)
            diag["url_after_apply"]=page.url
            try: page.wait_for_load_state("networkidle",timeout=8000)
            except Exception: pass
        # Prefer Workday's resume-assisted flow. It parses the approved resume
        # into My Information / My Experience and reduces brittle manual entry.
        manual=[
            'button:has-text("Autofill with Resume")','a:has-text("Autofill with Resume")',
            'button:has-text("Apply with Resume")','a:has-text("Apply with Resume")',
            'button:has-text("Use My Resume")','a:has-text("Use My Resume")',
            'button:has-text("Apply Manually")','a:has-text("Apply Manually")',
            'button:has-text("Apply without an account")','a:has-text("Apply without an account")'
        ]
        for sel in manual:
            try:
                loc=page.locator(sel).first
                if loc.count() and loc.is_visible():
                    diag["manual_selector"]=sel;loc.click(timeout=5000)
                    page.wait_for_timeout(1800);diag["url_after_manual"]=page.url
                    # Resume-assisted Workday flows commonly expose a file input
                    # immediately after choosing Autofill/Apply with Resume.
                    break
            except Exception:pass
        texts=page.locator("button, a, [role=button]").all_inner_texts()
        diag["visible_actions"]=[re.sub(r"\\s+"," ",x).strip() for x in texts if x.strip()][:50]
        body=page.locator("body").inner_text(timeout=5000)
        diag["body_excerpt"]=re.sub(r"\\s+"," ",body).strip()[:1200]
        nb=_norm(body)
        # Header Sign In links are normal on Workday; only classify an auth gate
        # when the page itself is not already inside /apply/.
        if "/apply/" not in page.url and any(x in nb for x in ("sign in","signin","log in","login")):diag["gate"]="SIGN_IN"
        if "/apply/" not in page.url and any(x in nb for x in ("create account","create an account")):
            diag["gate"]="CREATE_ACCOUNT" if not diag["gate"] else diag["gate"]+"+CREATE_ACCOUNT"
    except Exception as exc:
        diag["diagnostic_error"]=str(exc)
    diag["final_url"]=page.url
    return diag

def _required(el):
    return el.get_attribute("required") is not None or el.get_attribute("aria-required")=="true"

def _fill_current_page(page,item,identity,resume,result):
    """Fill only deterministic fields on the current ATS step."""
    before=len(result["filled"]);unresolved=[]
    try:
        body_hint=_norm(page.locator("body").inner_text(timeout=3000))
        if "how did you hear about us" in body_hint and _workday_source(page,"Company Website"):
            result["filled"].append({"field":"How Did You Hear About Us?","value":"Company Website"})
    except Exception:pass
    controls=page.locator("input, textarea, select")
    for i in range(min(controls.count(),250)):
        el=controls.nth(i)
        try:
            if not el.is_visible():continue
        except Exception:continue
        typ=(el.get_attribute("type") or "").lower();label=_label(el);required=_required(el)
        if typ in ("hidden","submit","button"):continue
        if typ=="file":
            fl=_norm(label)
            if any(t in fl for t in ("resume","cv","curriculum vitae")):
                try:el.set_input_files(str(resume.resolve()));result["filled"].append({"field":label or "resume","value":"validated PDF"})
                except Exception:
                    if required:unresolved.append(label or "resume upload")
            elif required:unresolved.append(label or "required file upload")
            continue
        x=_norm(label)
        if "phone extension" in x or x.endswith(" extension"):
            continue
        key=_field_key(label);value=identity.get(key) if key else _question_answer(label,item)
        if value not in (None,""):
            try:
                selected=False
                if "how did you hear about us" in x:
                    selected=_workday_select_dropdown(page,el,value)
                elif key=="phone":
                    digits=re.sub(r"\\D+","",str(value))[-10:]
                    formatted=f"({digits[:3]}) {digits[3:6]}-{digits[6:]}" if len(digits)==10 else digits
                    el.click();el.fill(formatted);el.press("Tab");page.wait_for_timeout(250)
                    selected=True
                else:
                    selected=_choose(el,value)
                if selected:result["filled"].append({"field":label,"value":value})
                elif required:unresolved.append(label)
            except Exception:
                if required:unresolved.append(label)
        elif required:
            current=""
            try:current=el.input_value()
            except Exception:pass
            # Workday searchable comboboxes can have an empty backing input even
            # when a required value is already selected and rendered beside it.
            lx=_norm(label)
            selected_hint=any(t in lx for t in ("item selected","items selected"))
            if "country phone code" in lx and ("united states" in lx or "+1" in label):
                selected_hint=True
            if not current and not selected_hint:unresolved.append(label or f"field_{i}")
    return len(result["filled"])-before,sorted(set(unresolved))

def _workday_steps(page,item,identity,resume,result,max_steps=8):
    """Advance Workday step-by-step only while every required field is safely answered."""
    steps=[]
    for n in range(1,max_steps+1):
        page.wait_for_timeout(1500)
        # Workday often paints the step shell first and keeps the actual form
        # behind a transient "Loading" state. Do not inspect/advance that shell.
        for _ in range(20):
            try:
                body_now=page.locator("body").inner_text(timeout=3000)
                interactive=page.locator('input:not([type="hidden"]), textarea, select, [role="combobox"]').count()
                if "Loading" not in body_now and interactive>0:break
            except Exception:pass
            page.wait_for_timeout(500)
        filled,unresolved=_fill_current_page(page,item,identity,resume,result)
        body=page.locator("body").inner_text(timeout=7000)
        step={"step":n,"url":page.url,"filled_count":filled,"unresolved_required":unresolved,
              "body_excerpt":re.sub(r"\\s+"," ",body).strip()[:800]}
        # Capture exact DOM metadata for stubborn Workday custom controls. This is
        # intentionally diagnostic: do not claim a field is filled until Workday accepts it.
        if "how did you hear about us" in _norm(body):
            try:
                src=page.locator('input[data-automation-id="source--source"], input[id*="source--source"], [data-automation-id="source--source"] input').first
                if src.count():
                    step["source_control"]={
                        "tag":src.evaluate("e=>e.tagName"),"type":src.get_attribute("type"),
                        "role":src.get_attribute("role"),"id":src.get_attribute("id"),
                        "automation_id":src.get_attribute("data-automation-id"),
                        "aria_controls":src.get_attribute("aria-controls"),
                        "aria_expanded":src.get_attribute("aria-expanded"),
                        "value":src.input_value() if src.evaluate("e=>'value' in e") else None,
                        "outer_html":src.evaluate("e=>e.outerHTML")[:1800]
                    }
                step["visible_options"]=[re.sub(r"\\s+"," ",x).strip() for x in page.locator('[role="option"], [data-automation-id*="promptOption"]').all_inner_texts() if x.strip()][:50]
            except Exception as exc:step["source_diagnostic_error"]=str(exc)
            try:
                ph=page.locator('input[data-automation-id="phoneNumber"], input[id*="phoneNumber--phoneNumber"]').first
                if ph.count():
                    step["phone_control"]={"value":ph.input_value(),"type":ph.get_attribute("type"),
                        "pattern":ph.get_attribute("pattern"),"maxlength":ph.get_attribute("maxlength"),
                        "outer_html":ph.evaluate("e=>e.outerHTML")[:1800]}
            except Exception as exc:step["phone_diagnostic_error"]=str(exc)
        steps.append(step)
        if BLOCKER_RE.search(body):
            result["blockers"].append("CAPTCHA/MFA/verification challenge detected");break
        if unresolved:break
        # A rendered Workday step with no mapped controls is not safe to advance:
        # capture its DOM shape so custom Workday widgets can be mapped next.
        visible_inputs=page.locator('input:not([type="hidden"]), textarea, select, [role="combobox"]').count()
        if filled==0 and visible_inputs==0:
            step["render_state"]="NO_INTERACTIVE_CONTROLS"
            try:
                step["automation_ids"]=page.locator("[data-automation-id]").evaluate_all(
                    "els => [...new Set(els.map(e=>e.getAttribute('data-automation-id')).filter(Boolean))].slice(0,120)"
                )
            except Exception:step["automation_ids"]=[]
            break
        # Never click Submit. Only advance intermediate Workday pages.
        nxt=None
        for sel in ('button:has-text("Save and Continue")','button:has-text("Next")',
                    '[data-automation-id="bottom-navigation-next-button"]'):
            try:
                loc=page.locator(sel).first
                if loc.count() and loc.is_visible() and loc.is_enabled():nxt=loc;step["next_selector"]=sel;break
            except Exception:pass
        if nxt is None:break
        try:
            before_url=page.url
            before_text=_norm(body)
            nxt.click(timeout=7000);page.wait_for_timeout(1800)
            after=page.locator("body").inner_text(timeout=5000)
            # Do not loop on a Workday step that rejected Next with validation errors.
            if ("errors found" in _norm(after) or "error " in _norm(after)) and page.url==before_url:
                step["validation_errors"]=re.sub(r"\\s+"," ",after).strip()[:1200]
                result["blockers"].append("Workday validation errors remain on current step")
                break
        except Exception as exc:
            step["next_error"]=str(exc);break
    return steps

def autofill(item:dict,headless=True,review_seconds=0)->dict:
    """Fill deterministic fields and upload the validated PDF. Never submit."""
    profile=load_profile();identity=_identity(profile);url=item.get("url")
    result={"external_id":item.get("external_id"),"url":url,"status":"FILLING","filled":[],"unresolved_required":[],"blockers":[],"submitted":False,"navigation":None}
    resume=_resolve_resume(item.get("resume_path"))
    if resume is None:
        return {**result,"status":"MANUAL_ACTION_REQUIRED","reason":"Validated resume file is missing","expected_resume_path":item.get("resume_path")}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=headless);page=browser.new_page()
        try:
            page.goto(url,wait_until="domcontentloaded",timeout=60000)
            if (item.get("ats_provider") or "").lower()=="workday":
                result["navigation"]=_workday_enter_application(page)
                # If resume-assisted flow is selected, upload the exact validated
                # PDF before scanning the generated application fields.
                chosen=(result["navigation"] or {}).get("manual_selector") or ""
                if "Resume" in chosen:
                    try:
                        file_inputs=page.locator('input[type="file"]')
                        for fi in range(file_inputs.count()):
                            inp=file_inputs.nth(fi)
                            try:
                                inp.set_input_files(str(resume.resolve()))
                                result["filled"].append({"field":"Workday resume import","value":"validated PDF"})
                                break
                            except Exception:pass
                        page.wait_for_timeout(3500)
                    except Exception:pass
            body=page.locator("body").inner_text(timeout=10000)
            if BLOCKER_RE.search(body):
                result["blockers"].append("CAPTCHA/MFA/verification challenge detected");result["status"]="MANUAL_ACTION_REQUIRED";return result
            if (item.get("ats_provider") or "").lower()=="workday":
                result["workday_steps"]=_workday_steps(page,item,identity,resume,result)
                result["unresolved_required"]=sorted(set(q for s in result["workday_steps"] for q in s.get("unresolved_required",[])))
            else:
                _,result["unresolved_required"]=_fill_current_page(page,item,identity,resume,result)
            # A page with zero mapped fields is not a successful autofill. Workday
            # commonly lands on a job-description/sign-in step before its application form.
            if not result["filled"]:
                result["status"]="MANUAL_ACTION_REQUIRED"
                result["reason"]="No application form fields were mapped; application form may require an Apply/sign-in step."
            else:
                result["status"]="MANUAL_ACTION_REQUIRED" if result["unresolved_required"] else "AUTOFILLED_REVIEW_REQUIRED"
        except Exception as exc:
            result["status"]="MANUAL_ACTION_REQUIRED";result["reason"]=str(exc)
        finally:
            if not headless and review_seconds>0:
                print(f"Browser will stay open for {review_seconds} seconds for review...")
                page.wait_for_timeout(review_seconds*1000)
            browser.close()
    return result

def run(queue_path="generated/application_queue.json",output="generated/application_autofill.json",limit=None,headless=True,review_seconds=0):
    rows=json.loads(Path(queue_path).read_text(encoding="utf-8"));results=[]
    for item in rows:
        if item.get("status")!="READY_FOR_ATS_ADAPTER":continue
        if limit is not None and len(results)>=limit:break
        results.append(autofill(item,headless,review_seconds))
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(results,indent=2),encoding="utf-8");return results

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--queue",default="generated/application_queue.json");ap.add_argument("--output",default="generated/application_autofill.json");ap.add_argument("--limit",type=int);ap.add_argument("--headed",action="store_true");ap.add_argument("--review-seconds",type=int,default=0);a=ap.parse_args()
    rows=run(a.queue,a.output,a.limit,not a.headed,a.review_seconds);print(json.dumps({"processed":len(rows),"autofilled_review_required":sum(x["status"]=="AUTOFILLED_REVIEW_REQUIRED" for x in rows),"manual_action":sum(x["status"]=="MANUAL_ACTION_REQUIRED" for x in rows),"output":a.output},indent=2))
