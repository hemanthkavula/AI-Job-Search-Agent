from __future__ import annotations
import argparse,json,re,os
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.config import load_profile
from app.application_inspector import BLOCKER_RE
from app.application_navigator import enter_application, form_scope, analyze as analyze_application
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def _norm(s):return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()

def _application_credentials(provider=None):
    """Load ATS credentials from local environment only; Dice can override the generic login."""
    if (provider or "").strip().lower()=="dice":
        email=(os.getenv("DICE_LOGIN_EMAIL") or "").strip()
        password=os.getenv("DICE_LOGIN_PASSWORD") or ""
        if email and password:
            return {"email":email,"password":password}
    return {
        "email": (os.getenv("APPLICATION_LOGIN_EMAIL") or "").strip(),
        "password": os.getenv("APPLICATION_LOGIN_PASSWORD") or "",
    }

def _fill_login_gate(scope,result):
    """Fill deterministic login credentials without logging or persisting the password."""
    creds=_application_credentials()
    if not creds["email"] or not creds["password"]:
        return False
    email_sel='input[type="email"], input[name*="email" i], input[id*="email" i], input[autocomplete="username"]'
    pass_sel='input[type="password"], input[autocomplete="current-password"]'
    try:
        email=scope.locator(email_sel).first
        password=scope.locator(pass_sel).first
        if not email.count() or not password.count() or not email.is_visible() or not password.is_visible():
            return False
        email.fill(creds["email"])
        password.fill(creds["password"])
        result.setdefault("filled",[]).append({"field":"ATS login email","value":creds["email"]})
        result.setdefault("filled",[]).append({"field":"ATS login password","value":"[REDACTED]"})
        result["login_credentials_filled"]=True
        return True
    except Exception as exc:
        result["login_credentials_error"]=str(exc)
        return False

def _dice_email_continue(page,result):
    """Dice uses an email-first auth gate; advance it before password sign-in/account creation."""
    if "dice.com/dashboard/login" not in page.url:return {"handled":False}
    creds=_application_credentials("dice")
    if not creds["email"]:return {"handled":False,"reason":"APPLICATION_LOGIN_EMAIL not configured"}
    try:
        email=page.locator('input[type="email"], input[name*="email" i], input[id*="email" i]').first
        if not email.count() or not email.is_visible():return {"handled":False,"reason":"Dice email field not found"}
        email.fill(creds["email"])
        actions=page.locator('button, [role="button"], input[type="submit"]')
        for i in range(min(actions.count(),60)):
            a=actions.nth(i)
            try:
                tag=a.evaluate("(e)=>e.tagName.toLowerCase()")
                txt=_norm((a.get_attribute("value") if tag=="input" else a.inner_text()) or "")
                if a.is_visible() and a.is_enabled() and txt=="continue with email":
                    a.click(timeout=5000)
                    result.setdefault("filled",[]).append({"field":"Dice account email","value":creds["email"]})
                    result["dice_email_gate_advanced"]=True
                    page.wait_for_timeout(1800)
                    try:page.wait_for_load_state("domcontentloaded",timeout=7000)
                    except Exception:pass
                    return {"handled":True}
            except Exception:pass
        return {"handled":False,"reason":"Dice Continue with email action not found"}
    except Exception as exc:return {"handled":False,"reason":str(exc)}

def _workday_open_email_auth(page):
    """Open Workday's email authentication form when the tenant first shows provider choices."""
    try:
        actions=page.locator('button, [role="button"], a')
        for i in range(min(actions.count(),80)):
            a=actions.nth(i)
            try:
                if not a.is_visible() or not a.is_enabled():continue
                txt=_norm(a.inner_text() or a.get_attribute("aria-label") or "")
                if txt in ("sign in with email","continue with email","use email","email"):
                    a.click(timeout=5000)
                    page.wait_for_timeout(1000)
                    return {"handled":True,"action":txt}
            except Exception:pass
    except Exception as exc:
        return {"handled":False,"reason":str(exc)}
    return {"handled":False}

def _auth_action(scope, result):
    """Sign in or create an ATS account using local env credentials. Never handles CAPTCHA/MFA."""
    try:
        scope_url=(scope.page.url if hasattr(scope,"page") else scope.url)
    except Exception:
        scope_url=""
    creds=_application_credentials("dice" if "dice.com" in (scope_url or "").lower() else None)
    if not creds["email"] or not creds["password"]:
        return {"handled":False,"reason":"APPLICATION_LOGIN_EMAIL/PASSWORD not configured"}
    try:
        body=_norm(scope.locator("body").inner_text(timeout=5000))
    except Exception:
        body=""
    if BLOCKER_RE.search(body):
        return {"handled":False,"blocker":"CAPTCHA/MFA/verification challenge detected"}

    # Workday account creation frequently renders Email Address as type=text
    # with data-automation-id=email, so do not rely on input[type=email].
    emails=scope.locator(
        'input[data-automation-id="email"], input[type="email"], '
        'input[name*="email" i], input[id*="email" i], input[autocomplete="username"]'
    )
    passwords=scope.locator(
        'input[data-automation-id="password"], input[data-automation-id="verifyPassword"], '
        'input[type="password"], input[autocomplete="current-password"], input[autocomplete="new-password"]'
    )
    email=next((emails.nth(i) for i in range(min(emails.count(),20)) if emails.nth(i).is_visible()),None)
    password=next((passwords.nth(i) for i in range(min(passwords.count(),20))
                   if passwords.nth(i).is_visible() and
                   _norm(passwords.nth(i).get_attribute("data-automation-id") or "")!="verify password"),None)
    # Email-first login flows (notably Dice) no longer expose an editable email
    # field on the password page. The email was already accepted on the prior step.
    if password is None:
        return {"handled":False,"reason":"No visible login/account password field detected"}
    try:
        if email is not None:
            email.fill(creds["email"])
            # Workday/React controlled inputs can reject a fill that did not stick.
            if (email.input_value() or "").strip()!=creds["email"]:
                email.click();email.press("Control+A");email.press_sequentially(creds["email"],delay=35)
        password.fill(creds["password"])
        logged=[{"field":"ATS account password","value":"[REDACTED]"}]
        if email is not None:logged.insert(0,{"field":"ATS account email","value":creds["email"]})
        result.setdefault("filled",[]).extend(logged)
        # Account creation commonly requires a distinct Verify New Password field.
        confirms=scope.locator('input[data-automation-id="verifyPassword"], input[type="password"]')
        for i in range(min(confirms.count(),6)):
            try:
                confirm=confirms.nth(i)
                if not confirm.is_visible():continue
                aid=_norm(confirm.get_attribute("data-automation-id") or "")
                if aid=="verify password" or confirm!=password:
                    # Avoid overwriting the primary field; fill only empty/verify fields.
                    if aid=="verify password" or not confirm.input_value():
                        confirm.fill(creds["password"])
            except Exception:pass
        result["auth_field_verification"]={
            "email_present": email is not None,
            "email_filled": bool(email is not None and (email.input_value() or "").strip()==creds["email"]),
            "password_filled": bool(password.input_value()),
            "verify_password_filled": any(
                confirms.nth(i).is_visible() and bool(confirms.nth(i).input_value())
                for i in range(min(confirms.count(),6))
            ) if confirms.count() else False,
        }
        actions=scope.locator('button, input[type="submit"], [role="button"]')
        create_mode=any(t in body for t in ("create account","create an account","register","sign up"))
        if create_mode:
            # Workday commonly disables Create Account until its explicit privacy/
            # account-processing acknowledgement is checked.
            checks=scope.locator('input[type="checkbox"]')
            for i in range(min(checks.count(),20)):
                cb=checks.nth(i)
                try:
                    if not cb.is_visible():continue
                    ctx=_norm(_label(cb))
                    aid=_norm(cb.get_attribute("data-automation-id") or "")
                    if ("consent" in ctx or "privacy" in ctx or "acknowledge" in ctx or
                        "create account checkbox" in aid):
                        if not cb.is_checked():cb.check(force=True)
                        if cb.is_checked():
                            result.setdefault("filled",[]).append({"field":"ATS account privacy acknowledgement","value":"accepted"})
                except Exception:pass
            try:scope.page.wait_for_timeout(400) if hasattr(scope,"page") else None
            except Exception:pass
        patterns=("create account","register","sign up","continue") if create_mode else ("sign in","log in","login","continue")
        for wanted in patterns:
            for i in range(min(actions.count(),80)):
                a=actions.nth(i)
                try:
                    txt=_norm((a.inner_text() if a.evaluate("(e)=>e.tagName.toLowerCase()")!="input" else a.get_attribute("value")) or "")
                    if a.is_visible() and wanted in txt and not any(x in txt for x in ("submit application","send application","complete application")):
                        a.click(timeout=5000)
                        result["auth_action"]="CREATE_ACCOUNT" if create_mode else "SIGN_IN"
                        return {"handled":True,"action":result["auth_action"]}
                except Exception: pass
        return {"handled":False,"reason":"Credentials filled but no safe authentication action found"}
    except Exception as exc:
        return {"handled":False,"reason":str(exc)}

def _identity(profile):
    parts=(profile.get("name") or "").split()
    contact=profile.get("contact") or {}
    address=contact.get("address") or {}
    raw_phone=contact.get("phone","")
    digits=re.sub(r"\D+","",raw_phone)
    us_phone=digits[-10:] if len(digits)>=10 else digits
    return {"first_name":parts[0] if parts else "","last_name":parts[-1] if len(parts)>1 else "",
            "full_name":profile.get("name",""),"email":contact.get("email",""),"phone":us_phone,
            "linkedin":contact.get("linkedin",""),"address_line1":address.get("line1",""),
            "city":address.get("city",""),"state":address.get("state",""),
            "postal_code":address.get("postal_code",""),"country":address.get("country","")}

def _field_key(label):
    x=_norm(label)
    if "phone extension" in x or x.endswith(" extension") or "country phone code" in x:return None
    rules=(("first name","first_name"),("last name","last_name"),("full name","full_name"),("email","email"),
           ("phone number","phone"),("mobile","phone"),("linkedin","linkedin"),
           ("street address","address_line1"),("address line 1","address_line1"),("address 1","address_line1"),
           ("postal code","postal_code"),("zip code","postal_code"),("zipcode","postal_code"),
           ("city","city"),("state","state"),("country","country"))
    return next((k for token,k in rules if token in x),None)

def _profile_evidence_text(profile):
    chunks=[]
    for skill in profile.get("skills") or []:chunks.append(str(skill))
    for category,values in (profile.get("skill_categories") or {}).items():
        chunks.append(str(category));chunks.extend(str(v) for v in (values or []))
    for role in profile.get("experience") or []:
        chunks.extend([str(role.get("title") or ""),str(role.get("company") or ""),str(role.get("environment") or "")])
        chunks.extend(str(v) for v in (role.get("evidence") or []))
    chunks.extend(str(v) for v in (profile.get("summary_source") or []))
    return _norm(" ".join(chunks))

def _technical_question_answer(label,profile):
    """Answer only narrow, evidence-backed technical yes/no and years questions."""
    x=_norm(label);evidence=_profile_evidence_text(profile)
    if not x or not evidence:return None
    if not any(t in x for t in ("experience","experienced","worked with","hands on","proficient","knowledge of","years")):
        return None
    aliases={
        "python":("python",),"sql":("sql",),"pyspark":("pyspark",),"spark":("apache spark","spark"),
        "databricks":("databricks",),"snowflake":("snowflake",),"kafka":("kafka",),
        "airflow":("airflow",),"dbt":("dbt",),"terraform":("terraform",),"docker":("docker",),
        "kubernetes":("kubernetes",),"aws":("aws","amazon web services"),"azure":("azure",),
        "redshift":("redshift",),"glue":("aws glue","glue"),"bigquery":("bigquery",),
        "flink":("flink",),"beam":("apache beam","beam"),"dagster":("dagster",),
    }
    asked=[]
    for canonical,names in aliases.items():
        if any(re.search(r"\b"+re.escape(name)+r"\b",x) for name in names):asked.append((canonical,names))
    if not asked:return None
    supported=all(any(re.search(r"\b"+re.escape(name)+r"\b",evidence) for name in names) for _,names in asked)
    # Never invent technology-specific year counts. Only the profile's explicit
    # overall experience may answer a generic total-experience question.
    if "years" in x:
        tech_specific=any(canonical for canonical,_ in asked)
        if tech_specific:return None
        years=profile.get("candidate_experience_years")
        return str(years) if years is not None else None
    if any(t in x for t in ("do you","have you","are you","experience with","experienced with","worked with","proficient")):
        return "Yes" if supported else None
    return None

def _open_ended_answer(label,item,profile):
    """Build short application prose only from explicit profile evidence and the current job."""
    x=_norm(label)
    if not x:return None
    summary=[str(v).strip() for v in (profile.get("summary_source") or []) if str(v).strip()]
    roles=profile.get("experience") or []
    if any(t in x for t in ("complex pipeline","data pipeline","pipeline you built","pipeline you designed","technical project","project you")):
        evidence=[]
        for role in roles:
            for line in role.get("evidence") or []:
                lx=_norm(line)
                if any(t in lx for t in ("pipeline","etl","streaming","ingest")):
                    evidence.append(str(line).strip())
            if evidence:break
        if evidence:
            return " ".join(evidence[:2])
    if any(t in x for t in ("why are you interested","why interested","why this role","why do you want","what interests you","drawn to this role")):
        title=(item.get("title") or "this data engineering role").strip()
        jd=_norm(item.get("description") or "")
        supported=[]
        skill_pool=profile.get("priority_skills") or profile.get("skills") or []
        for skill in skill_pool:
            token=_norm(str(skill))
            if token and token in jd:supported.append(str(skill))
        # If the fixture/profile has no explicit summary, ground the interest answer
        # in the first documented role/evidence rather than fabricating prose.
        if summary:
            base=summary[0]
        else:
            base=""
            for role in roles:
                evidence=[str(v).strip() for v in (role.get("evidence") or []) if str(v).strip()]
                if evidence:
                    base=evidence[0]
                    break
        if base:
            if supported:
                return f"I'm interested in {title} because it aligns with my data engineering background, particularly {', '.join(supported[:4])}. {base}"
            return f"I'm interested in {title} because it aligns with my data engineering background. {base}"
    if any(t in x for t in ("tell us about yourself","tell me about yourself","briefly describe your experience","summarize your experience")) and summary:
        return " ".join(summary[:2])
    return None

def _question_answer(label,item,profile=None):
    x=_norm(label);known=item.get("known_answers") or {};profile=profile or {}
    prefs=profile.get("application_preferences") or {}
    disclosures=prefs.get("voluntary_disclosures") or {}
    relocation=prefs.get("relocation") or {}
    if "how did you hear about us" in x:return known.get("source") or "Company Website"
    if "previously employed" in x or ("employed by" in x and "past" in x):return known.get("previously_employed_by_company") or "No"
    if "authorized" in x and ("work" in x or "employment" in x):return known.get("authorized_to_work_us")
    # Combined "now or in the future" questions must be Yes for future H-1B need.
    if ("sponsor" in x or "sponsorship" in x) and ("future" in x or "later" in x):return known.get("requires_future_sponsorship")
    if ("sponsor" in x or "sponsorship" in x) and ("now" in x or "currently" in x):return known.get("requires_sponsorship_now")
    if "sponsor" in x or "sponsorship" in x:return known.get("requires_future_sponsorship")
    if "18 years" in x or "legal working age" in x:return "Yes" if prefs.get("legal_working_age") else None
    if "background check" in x:return "Yes" if prefs.get("background_check_willing") else None
    if "relocat" in x:return "Yes" if relocation.get("willing_to_relocate") else "No"
    if "veteran" in x:return disclosures.get("veteran_status")
    if "disability" in x:return disclosures.get("disability_status")
    if "gender" in x or x=="sex":return disclosures.get("gender")
    if "ethnicity" in x or "race" in x:return disclosures.get("ethnicity")
    technical=_technical_question_answer(label,profile)
    if technical is not None:return technical
    return _open_ended_answer(label,item,profile)

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


def _source_option_score(text,item=None,page_url=""):
    """Rank the actual source choices using this application's provenance and employer context."""
    x=_norm(text)
    if not x:return -1
    item=item or {}
    company=_norm(item.get("company") or "")
    source=_norm(item.get("source") or "")
    # Never claim a referral/recruiter/school relationship unless provenance says so.
    if any(t in x for t in ("employee referral","referral","recruiter","staffing agency","university","school","college")):
        return 100 if any(t in source for t in x.split()) else -1
    score=0
    # Exact employer/career-site choices are strongest (e.g. Adobe.com).
    company_tokens=[t for t in company.split() if len(t)>=4 and t not in ("inc","corp","corporation","company","llc")]
    if company_tokens and any(t in x for t in company_tokens):score=max(score,100)
    if any(t in x for t in ("company website","company career","career website","career site",
                            "corporate website","employer website","company site","career page","corporate site")):
        score=max(score,95)
    # If the discovery provenance itself is represented, prefer that truthful source.
    aliases={"linkedin":"linkedin","dice":"dice","indeed":"indeed","ziprecruiter":"ziprecruiter",
             "glassdoor":"glassdoor","monster":"monster","jobright":"jobright"}
    for token,label in aliases.items():
        if token in source and label in x:score=max(score,90)
    if "website" in x or x in ("internet","online","web","other website","other online source"):
        score=max(score,70)
    if any(t in x for t in ("other","not listed","none of the above")):score=max(score,30)
    return score if score else -1

def _workday_select_dropdown(page,el,value,item=None):
    """Inspect this tenant's real choices and select the best truthful source for this application."""
    try:
        el.click(timeout=3000);page.wait_for_timeout(900)
        selectors='[role="option"], [data-automation-id="promptOption"], [data-automation-id="promptOptionText"], [data-uxi-widget-type="selectoption"], [data-uxi-widget-type="option"]'
        def collect():
            rows=[];opts=page.locator(selectors)
            for i in range(min(opts.count(),350)):
                o=opts.nth(i)
                try:
                    if o.is_visible():
                        txt=re.sub(r"\\s+"," ",o.inner_text() or "").strip()
                        if txt and len(txt)<180 and _norm(txt) not in ("expanded","collapsed","search","select one"):rows.append((txt,o))
                except Exception:pass
            return rows
        rows=collect()
        if not rows:
            try:el.press("ArrowDown");page.wait_for_timeout(700)
            except Exception:pass
            rows=collect()
        ranked=[];seen=set()
        for txt,o in rows:
            nx=_norm(txt)
            if nx in seen:continue
            seen.add(nx);score=_source_option_score(txt,item,page.url)
            if score>=0:ranked.append((score,len(txt),txt,o))
        if not ranked:return False
        ranked.sort(key=lambda z:(-z[0],z[1]))
        _,_,chosen,opt=ranked[0]
        opt.click(timeout=3000);page.wait_for_timeout(600)
        try:
            container=el.locator("xpath=ancestor::*[@data-uxi-widget-type='selectinput' or @data-automation-id='formField'][1]")
            rendered=_norm(container.inner_text() if container.count() else el.locator("xpath=..").inner_text())
        except Exception:rendered=""
        return "0 items selected" not in rendered and (_norm(chosen) in rendered or el.input_value()=="")
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


def _wait_for_application_controls(page,timeout_ms=15000):
    elapsed=0
    while elapsed<timeout_ms:
        try:
            body=page.locator("body").inner_text(timeout=2500)
            controls=page.locator('input:not([type="hidden"]), textarea, select, [role="combobox"]').count()
            if "Loading" not in body and controls>0:return True
        except Exception:pass
        page.wait_for_timeout(500);elapsed+=500
    return False

def _application_preflight(page):
    """Analyze the current application page before filling it. Every application gets its own plan."""
    body=page.locator("body").inner_text(timeout=7000)
    controls=[]
    loc=page.locator('input, textarea, select, [role="combobox"], [role="radio"], [role="checkbox"]')
    for i in range(min(loc.count(),350)):
        el=loc.nth(i)
        try:
            if not el.is_visible():continue
            controls.append({
                "label":_label(el),
                "tag":el.evaluate("e=>e.tagName.toLowerCase()"),
                "type":el.get_attribute("type"),
                "required":_required(el),
                "id":el.get_attribute("id"),
                "name":el.get_attribute("name"),
                "automation_id":el.get_attribute("data-automation-id"),
            })
        except Exception:pass
    actions=[]
    for txt in page.locator("button, a, [role=button]").all_inner_texts()[:150]:
        txt=re.sub(r"\\s+"," ",txt or "").strip()
        if txt:actions.append(txt)
    return {
        "url":page.url,
        "body_excerpt":re.sub(r"\\s+"," ",body).strip()[:1800],
        "required_fields":[x for x in controls if x["required"]],
        "visible_fields":controls,
        "actions":actions[:80],
        "has_resume_upload":page.locator('input[type="file"]').count()>0,
        "blocker_detected":bool(BLOCKER_RE.search(body)),
    }

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

def _dice_card(page, heading):
    """Find the Dice document card by an exact visible heading, without crossing into sibling cards."""
    wanted=_norm(heading)
    # Dice renders "Resume *" and "Cover letter Optional" as ordinary text in
    # some builds, not semantic headings. Start from exact text nodes, then walk
    # upward only until we reach the smallest ancestor containing that document's
    # overflow button. This avoids ever selecting the sibling Cover Letter card.
    nodes=page.locator("text=/^(Resume\\s*\\*?|Cover letter(?:\\s+Optional)?)$/i")
    for i in range(min(nodes.count(),80)):
        h=nodes.nth(i)
        try:
            raw=_norm(h.inner_text())
            is_wanted=(wanted=="resume" and raw in ("resume","resume *")) or (
                wanted=="cover letter" and raw in ("cover letter","cover letter optional")
            )
            if not h.is_visible() or not is_wanted:continue
            node=h
            for _ in range(8):
                node=node.locator("xpath=parent::*")
                if not node.count():break
                txt=_norm(node.inner_text())
                has_resume=re.search(r"(^| )resume( |$)",txt) is not None
                has_cover="cover letter" in txt
                buttons=node.locator("button")
                visible_buttons=0
                for j in range(min(buttons.count(),10)):
                    try:
                        if buttons.nth(j).is_visible():visible_buttons+=1
                    except Exception:pass
                if not visible_buttons:continue
                if wanted=="resume" and has_resume and not has_cover:return node
                if wanted=="cover letter" and has_cover and not has_resume:return node
        except Exception:pass
    return None

def _dice_card_menu_action(page,card,action):
    """Use only the overflow/menu button contained by one verified Dice document card."""
    buttons=card.locator("button")
    menu=None
    for i in range(min(buttons.count(),20)):
        b=buttons.nth(i)
        try:
            if not b.is_visible():continue
            meta=_norm(" ".join(filter(None,[
                b.inner_text(),b.get_attribute("aria-label"),b.get_attribute("title"),
                b.get_attribute("data-testid"),b.get_attribute("data-automation-id"),
            ])))
            if any(t in meta for t in ("more","menu","options","ellipsis","overflow")):
                menu=b;break
        except Exception:pass
    if menu is None:
        # The screenshot shows the card overflow as an icon-only button. Accept
        # the sole visible button only when it is inside this already-isolated card.
        visible=[]
        for i in range(min(buttons.count(),20)):
            try:
                if buttons.nth(i).is_visible():visible.append(buttons.nth(i))
            except Exception:pass
        if len(visible)!=1:return False
        menu=visible[0]
    try:menu.click(timeout=3000)
    except Exception:return False
    page.wait_for_timeout(250)
    wanted=_norm(action)
    actions=page.locator('[role="menuitem"], [role="menu"] button, [role="menu"] li')
    for i in range(min(actions.count(),50)):
        a=actions.nth(i)
        try:
            if a.is_visible() and _norm(a.inner_text())==wanted:
                a.click(timeout=3000);return True
        except Exception:pass
    return False

def _dice_resume_upload(page,resume,result):
    """Replace only Dice's Resume card. Never interact with Cover Letter upload controls."""
    if "dice.com/job-applications/" not in (page.url or "").lower():
        return {"handled":False}
    expected=resume.name
    resume_card=_dice_card(page,"Resume")
    if resume_card is None:
        return {"handled":True,"verified":False,"reason":"Isolated Dice Resume card not found"}

    try:resume_text=resume_card.inner_text()
    except Exception:resume_text=""
    if expected not in resume_text:
        chooser_box={"chooser":None}
        def _capture_chooser(chooser):chooser_box["chooser"]=chooser
        page.once("filechooser",_capture_chooser)
        clicked=_dice_card_menu_action(page,resume_card,"Replace")
        if not clicked:
            try:page.remove_listener("filechooser",_capture_chooser)
            except Exception:pass
            return {"handled":True,"verified":False,"reason":"Resume-card Replace action not found; Cover Letter was not touched"}
        page.wait_for_timeout(500)
        chooser=chooser_box.get("chooser")
        if chooser is None:
            try:page.remove_listener("filechooser",_capture_chooser)
            except Exception:pass
            return {"handled":True,"verified":False,"reason":"Resume Replace did not emit a file chooser; refusing to use any page-level upload input"}
        try:
            chooser.set_files(str(resume.resolve()))
        except Exception as exc:
            return {"handled":True,"verified":False,"reason":f"Resume chooser could not be filled: {exc}"}
        page.wait_for_timeout(1500)

    resume_card=_dice_card(page,"Resume")
    try:resume_text=resume_card.inner_text() if resume_card is not None else ""
    except Exception:resume_text=""
    if expected not in resume_text:
        return {"handled":True,"verified":False,"reason":"Tailored filename did not appear in the isolated Dice Resume card","expected_filename":expected}

    result.setdefault("filled",[]).append({"field":"Dice resume","value":expected})
    result["dice_resume_verified"]=True
    return {"handled":True,"verified":True,"filename":expected}

def _required(el):
    return el.get_attribute("required") is not None or el.get_attribute("aria-required")=="true"

def _fill_current_page(page,item,identity,resume,result,profile=None):
    """Fill only deterministic fields on the current ATS step."""
    before=len(result["filled"]);unresolved=[]
    controls=page.locator("input, textarea, select")
    for i in range(min(controls.count(),250)):
        el=controls.nth(i)
        try:
            typ=(el.get_attribute("type") or "").lower()
        except Exception:continue
        if typ!="file":
            try:
                if not el.is_visible():continue
            except Exception:continue
        label=_label(el);required=_required(el)
        if typ in ("hidden","submit","button"):continue
        # Required consent checkboxes are safe to accept when they explicitly
        # reference the ATS privacy policy / terms needed to submit the application.
        if typ=="checkbox":
            try:
                consent_context=el.evaluate("""e => {
                  const p=e.closest('label, fieldset, div, p') || e.parentElement;
                  return ((p && (p.innerText || p.textContent)) || '') + ' ' +
                         (e.getAttribute('aria-label') || '') + ' ' +
                         (e.getAttribute('name') || '') + ' ' + (e.id || '');
                }""")
            except Exception:
                consent_context=label
            lx=_norm((label or "")+" "+(consent_context or ""))
            if any(t in lx for t in ("privacy policy","terms of service","terms and conditions","i agree","agreement")):
                try:
                    if not el.is_checked():el.check(force=True)
                    page.wait_for_timeout(200)
                    if not el.is_checked():raise RuntimeError("ATS consent checkbox did not remain checked")
                    result["filled"].append({"field":label or "required ATS consent","value":"accepted"})
                except Exception:
                    unresolved.append(label or "required ATS consent")
            elif required:
                unresolved.append(label or "required checkbox")
            continue
        if typ=="file":
            # File inputs must be classified from their own local field context.
            # Parent/container text can include both "Resume" and "Cover Letter"
            # (notably Dice), which previously caused the tailored resume to be
            # uploaded into an optional cover-letter input as well.
            try:
                file_context=el.evaluate("""e => {
                  const parts=[];
                  const add=v=>{if(v && !parts.includes(String(v).trim())) parts.push(String(v).trim())};
                  add(e.getAttribute('aria-label')); add(e.getAttribute('name')); add(e.id);
                  if(e.id){const l=document.querySelector('label[for="'+CSS.escape(e.id)+'"]');if(l)add(l.innerText||l.textContent)}
                  const own=e.closest('label');if(own)add(own.innerText||own.textContent);
                  const wrapper=e.closest('[data-testid], [data-automation-id], fieldset');
                  if(wrapper){
                    const heading=wrapper.querySelector('legend, label, h1, h2, h3, h4');
                    if(heading)add(heading.innerText||heading.textContent);
                  }
                  return parts.join(' | ');
                }""")
            except Exception:
                file_context=label
            fl=_norm(file_context)
            is_cover_letter=any(t in fl for t in ("cover letter","coverletter"))
            is_resume=any(t in fl for t in ("resume","curriculum vitae")) or re.search(r"\\bcv\\b",fl)
            if is_resume and not is_cover_letter:
                try:
                    el.set_input_files(str(resume.resolve()))
                    result["filled"].append({"field":file_context or "resume","value":"validated PDF"})
                except Exception:
                    if required:unresolved.append(file_context or "resume upload")
            elif required:
                unresolved.append(file_context or "required file upload")
            continue
        x=_norm(label)
        if "phone extension" in x or x.endswith(" extension"):
            continue
        key=_field_key(label);value=identity.get(key) if key else _question_answer(label,item,profile)
        if value not in (None,""):
            try:
                selected=False
                if "how did you hear about us" in x:
                    selected=_workday_select_dropdown(page,el,value,item)
                elif key=="phone":
                    digits=re.sub(r"\\D+","",str(value))[-10:]
                    # Workday uses a masked phone widget that needs key events. Generic
                    # ATS forms (including isolved) are safer with a direct fill so the
                    # leading area-code digits are not dropped.
                    if "myworkdayjobs.com" in page.url.lower() or "workday" in page.url.lower():
                        el.click();el.press("Control+A");el.press("Backspace");page.wait_for_timeout(150)
                        el.evaluate("(e)=>{e.focus();try{e.setSelectionRange(0,0)}catch(_){}}")
                        el.press_sequentially(digits,delay=80);page.wait_for_timeout(250)
                        el.press("Tab");page.wait_for_timeout(350)
                    else:
                        el.fill(digits);page.wait_for_timeout(150);el.press("Tab");page.wait_for_timeout(250)
                    current=re.sub(r"\\D+","",el.input_value())
                    # A masked widget must retain all ten national digits. Never
                    # treat a truncated value (for example only the last 7 digits)
                    # as successfully filled.
                    selected=current[-10:]==digits and len(current)>=10
                else:
                    selected=_choose(el,value)
                if selected:
                    if key=="phone":
                        logged_value=el.input_value()
                    elif "how did you hear about us" in x:
                        try:
                            parent_text=re.sub(r"\\s+"," ",el.locator("xpath=..").inner_text() or "").strip()
                            logged_value=parent_text or value
                        except Exception:logged_value=value
                    else:logged_value=value
                    result["filled"].append({"field":label,"value":logged_value})
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

def _normalized_field_value(key,value):
    text=str(value or "").strip()
    if key=="phone":return re.sub(r"\D+","",text)[-10:]
    if key in ("email","linkedin"):return text.lower().rstrip("/")
    if key=="postal_code":return re.sub(r"[^a-z0-9]","",text.lower())
    return _norm(text)

def _verify_deterministic_fields(scope,identity,result,correct=True):
    """Read back identity/address fields the ATS retained and repair safe mismatches once."""
    checks=[];failures=[]
    controls=scope.locator("input, textarea, select")
    for i in range(min(controls.count(),250)):
        el=controls.nth(i)
        try:
            if not el.is_visible():continue
            typ=(el.get_attribute("type") or "").lower()
            if typ in ("hidden","file","checkbox","radio","submit","button","password"):continue
            label=_label(el);key=_field_key(label)
            expected=identity.get(key) if key else None
            if expected in (None,""):continue
            try:actual=el.input_value()
            except Exception:continue
            expected_norm=_normalized_field_value(key,expected)
            actual_norm=_normalized_field_value(key,actual)
            check={"field":label,"key":key,"expected":expected,"actual":actual,"matched":actual_norm==expected_norm}
            if not check["matched"] and correct:
                try:
                    if key=="phone":
                        digits=re.sub(r"\D+","",str(expected))[-10:]
                        el.click();el.press("Control+A");el.press("Backspace")
                        if "myworkdayjobs.com" in scope.page.url.lower() if hasattr(scope,"page") else False:
                            el.press_sequentially(digits,delay=60)
                        else:el.fill(digits)
                    else:
                        _choose(el,expected)
                    el.press("Tab");scope.page.wait_for_timeout(250) if hasattr(scope,"page") else None
                    actual=el.input_value()
                    actual_norm=_normalized_field_value(key,actual)
                    check.update({"actual_after_correction":actual,"matched":actual_norm==expected_norm,"corrected":True})
                except Exception as exc:
                    check["correction_error"]=str(exc)
            if not check["matched"]:failures.append(label or key)
            checks.append(check)
        except Exception:continue
    result.setdefault("field_verification",[]).extend(checks)
    return sorted(set(failures))

def _workday_resume_step(page,resume,result):
    """Handle Workday's resume-assisted first step and advance only after upload is present."""
    try:
        # The SPA can show the resume page before the hidden file input is mounted.
        for _ in range(30):
            fi=page.locator('input[type="file"]').first
            if fi.count():break
            page.wait_for_timeout(500)
        else:return False,"resume file input did not render"
        fi.set_input_files(str(resume.resolve()))
        page.wait_for_timeout(2500)
        body=page.locator("body").inner_text(timeout=5000)
        # Workday may hide the native input after accepting the file; successful
        # upload is evidenced by a filename/remove/change control or nonempty files.
        accepted=False
        try:accepted=fi.evaluate("e=>e.files && e.files.length>0")
        except Exception:pass
        if not accepted:
            nb=_norm(body);accepted=resume.name.lower() in body.lower() or any(t in nb for t in ("remove file","change file","uploaded"))
        if not accepted:return False,"resume upload was not accepted"
        if not any(x.get("field")=="Workday resume import" for x in result["filled"]):
            result["filled"].append({"field":"Workday resume import","value":"validated PDF"})
        nxt=page.locator('[data-automation-id="bottom-navigation-next-button"], button:has-text("Next")').first
        if not nxt.count() or not nxt.is_visible() or not nxt.is_enabled():return False,"resume step Next button unavailable"
        nxt.click(timeout=7000);page.wait_for_timeout(2500)
        return True,None
    except Exception as exc:return False,str(exc)

def _workday_steps(page,item,identity,resume,result,profile=None,max_steps=8):
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
        preflight=_application_preflight(page)
        pre_body=_norm(preflight.get("body_excerpt") or "")
        file_inputs=page.locator('input[type="file"]').count()
        actual_resume_step=(
            file_inputs>0 or
            ("upload either doc" in pre_body) or
            ("autofill with resume" in pre_body and "current step 2" in pre_body)
        )
        if actual_resume_step:
            ok,err=_workday_resume_step(page,resume,result)
            steps.append({"step":n,"url":page.url,"resume_step":True,"resume_uploaded":ok,"resume_error":err,
                          "preflight_required_fields":preflight["required_fields"],
                          "preflight_visible_field_count":len(preflight["visible_fields"])})
            if not ok:
                result["blockers"].append("Workday resume upload/advance failed")
                break
            continue
        filled,unresolved=_fill_current_page(page,item,identity,resume,result,profile)
        verification_failures=_verify_deterministic_fields(page,identity,result)
        unresolved=sorted(set(unresolved+verification_failures))
        body=page.locator("body").inner_text(timeout=7000)
        step={"step":n,"url":page.url,"filled_count":filled,"unresolved_required":unresolved,
              "body_excerpt":re.sub(r"\\s+"," ",body).strip()[:800],
              "preflight_required_fields":preflight["required_fields"],
              "preflight_visible_field_count":len(preflight["visible_fields"])}
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
                step["visible_options"]=[re.sub(r"\\s+"," ",x or "").strip() for x in page.locator('[role="option"], [data-automation-id="promptOption"], [data-automation-id="promptOptionText"], [data-uxi-widget-type="selectoption"], [data-uxi-widget-type="option"]').all_inner_texts() if (x or "").strip()][:80]
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

def _submission_confirmation(page):
    """Require positive ATS confirmation evidence after a final-submit click."""
    try:
        # External ATS forms may POST and redirect asynchronously. Give the submit
        # transition time to settle before deciding confirmation is absent.
        page.wait_for_timeout(3000)
        try:page.wait_for_load_state("domcontentloaded",timeout=8000)
        except Exception:pass
        body=_norm(page.locator("body").inner_text(timeout=8000))
    except Exception:
        body=""
    phrases=(
        "application submitted","application has been submitted","thank you for applying",
        "thanks for applying","we received your application","we have received your application",
        "application received","your application was received","successfully submitted",
    )
    matched=next((p for p in phrases if p in body),None)
    url=_norm(page.url)
    url_signal=any(x in url for x in ("confirmation","thank-you","thankyou","submitted","success"))

    # Dice can accept the application without navigating away from the wizard or
    # rendering a success phrase. On its final review page, successful submission
    # removes the irreversible Submit control while leaving the review content in
    # place. Treat that transition as Dice-specific positive evidence only when we
    # are still on the Dice application wizard and the page still identifies the
    # final review step.
    dice_review_submitted=False
    if "dice.com/job-applications/" in url and "/wizard" in url and (
        "step 2 of 2" in body or "review your application" in body
    ):
        try:
            submit_visible=False
            for sel in ('button','[role="button"]','input[type="submit"]','input[type="button"]'):
                loc=page.locator(sel)
                for i in range(min(loc.count(),80)):
                    el=loc.nth(i)
                    try:
                        if not el.is_visible():continue
                        tag=el.evaluate("(e)=>e.tagName.toLowerCase()")
                        txt=(el.get_attribute("value") if tag=="input" else el.inner_text()) or el.get_attribute("aria-label") or ""
                        if _norm(txt)=="submit":
                            submit_visible=True
                            break
                    except Exception:pass
                if submit_visible:break
            dice_review_submitted=not submit_visible
        except Exception:pass

    return {
        "confirmed":bool(matched or url_signal or dice_review_submitted),
        "matched_phrase":matched,
        "url":page.url,
        "url_signal":url_signal,
        "dice_review_submit_disappeared":dice_review_submitted,
        "body_excerpt":body[:1200],
    }

def _final_submit_candidates(page):
    """Find final-submit controls across the main document and accessible ATS frames."""
    candidates=[]
    for scope in [page]+[f for f in page.frames if f != page.main_frame]:
        for sel in ('button','[role="button"]','input[type="submit"]','input[type="button"]'):
            loc=scope.locator(sel)
            for i in range(min(loc.count(),160)):
                el=loc.nth(i)
                try:
                    if not el.is_visible() or not el.is_enabled():continue
                    tag=el.evaluate("(e)=>e.tagName.toLowerCase()")
                    txt=(el.get_attribute("value") if tag=="input" else el.inner_text()) or el.get_attribute("aria-label") or ""
                    nx=_norm(txt)
                    exact=nx in ("submit application","send application","complete application","finish application")
                    # A bare "Submit" is acceptable only for a submit-type control inside
                    # the application form after all required questions are resolved.
                    typ=(el.get_attribute("type") or "").lower()
                    # Dice renders its final control as a normal <button>
                    # labelled "Submit" rather than type="submit". _generic_steps
                    # already recognizes that exact review-boundary control, so
                    # final-submit lookup must use the same rule.
                    bare_submit=nx=="submit" and (typ=="submit" or tag=="button")
                    # Some external ATS forms use employer-specific final labels such
                    # as "Apply for this Position" rather than "Submit Application".
                    apply_position=nx in ("apply for this position","apply for position") and (
                        typ=="submit" or tag=="button"
                    )
                    if exact or bare_submit or apply_position:
                        candidates.append((0 if exact or apply_position else 1,len(nx),el,txt,getattr(scope,"url",page.url)))
                except Exception:pass
    candidates.sort(key=lambda x:(x[0],x[1]))
    return candidates

def _find_final_submit(page):
    rows=_final_submit_candidates(page)
    return rows[0] if rows else None

def _visible_validation_errors(page):
    """Capture visible ATS validation messages after a final-submit attempt."""
    rows=[]
    try:
        loc=page.locator('[role="alert"], .error, .errors, .alert-danger, .invalid-feedback, [class*="error" i]')
        for i in range(min(loc.count(),80)):
            el=loc.nth(i)
            try:
                if el.is_visible():
                    txt=re.sub(r"\\s+"," ",el.inner_text() or "").strip()
                    if txt and any(p in _norm(txt) for p in ("error","required","missing","please complete","please enter","invalid")):
                        rows.append(txt)
            except Exception:pass
    except Exception:pass
    return list(dict.fromkeys(rows))[:20]

def _generic_steps(page,item,identity,resume,result,profile=None,max_steps=12):
    """Fill and advance generic ATS pages, stopping before any final application submission."""
    steps=[]
    for step_no in range(1,max_steps+1):
        scope=form_scope(page)
        before_url=page.url
        before_filled=len(result["filled"])
        _,unresolved=_fill_current_page(scope,item,identity,resume,result,profile)
        verification_failures=_verify_deterministic_fields(scope,identity,result)
        unresolved=sorted(set(unresolved+verification_failures))
        analysis=analyze_application(page)
        step={"step":step_no,"url":before_url,"filled_count":len(result["filled"])-before_filled,
              "unresolved_required":unresolved,"analysis":analysis}
        steps.append(step)
        if analysis.get("blocker_detected"):
            result["blockers"].append("CAPTCHA/MFA/verification challenge detected")
            break
        if unresolved:
            break

        candidates=[]
        # Navigation controls can live outside the form element itself (Dice's
        # final Review/Submit page is one example). Search the selected form
        # scope first, then the page, while still only clicking safe intermediate
        # Next/Continue actions.
        action_scopes=[scope]
        if scope is not page:
            action_scopes.append(page)
        seen_actions=set()
        for action_scope in action_scopes:
            for sel in ('button','a','[role="button"]','input[type="button"]','input[type="submit"]'):
                loc=action_scope.locator(sel)
                for i in range(min(loc.count(),120)):
                    el=loc.nth(i)
                    try:
                        if not el.is_visible(): continue
                        tag=el.evaluate("(e)=>e.tagName.toLowerCase()")
                        txt=(el.get_attribute("value") if tag=="input" else el.inner_text()) or ""
                        nx=_norm(txt)
                        action_key=(sel,nx)
                        if action_key in seen_actions: continue
                        seen_actions.add(action_key)
                        typ=(el.get_attribute("type") or "").lower()
                        final_exact=nx in ("submit application","send application","complete application","finish application")
                        bare_submit=nx=="submit" and (typ=="submit" or tag=="button")
                        apply_position=nx in ("apply for this position","apply for position") and (typ=="submit" or tag=="button")
                        if final_exact or bare_submit or apply_position:
                            step["stopped_before_final_submit"]=True
                            step["final_submit_action"]=txt
                            step["final_submit_scope_url"]=getattr(action_scope,"url",page.url)
                            result["ready_for_final_submit"]=True
                            result["final_submit_action"]=txt
                            result["final_submit_scope_url"]=getattr(action_scope,"url",page.url)
                            return steps
                        score=0
                        if nx in ("next","continue","save and continue","save & continue"): score=100
                        elif "next" in nx or "continue" in nx: score=80
                        if score: candidates.append((score,len(nx),el,txt))
                    except Exception: pass
        if not candidates:
            step["reason"]="No safe intermediate Next/Continue action found"
            break
        candidates.sort(key=lambda x:(-x[0],x[1]))
        try:
            candidates[0][2].click(timeout=5000)
            step["advanced_with"]=candidates[0][3]
            page.wait_for_timeout(1200)
            try: page.wait_for_load_state("domcontentloaded",timeout=7000)
            except Exception: pass
            after=analyze_application(page)
            step["after_advance"]=after
            if after.get("blocker_detected"):
                result["blockers"].append("CAPTCHA/MFA/verification challenge detected")
                break
            if page.url==before_url and after.get("body_excerpt")==analysis.get("body_excerpt"):
                step["reason"]="Page did not advance after safe intermediate action"
                break
        except Exception as exc:
            step["reason"]=str(exc)
            break
    return steps

def autofill(item:dict,headless=True,review_seconds=0,inspect_only=False,wait_for_human_seconds=0,allow_submit=False,before_submit=None)->dict:
    """Inspect/fill deterministic fields and upload the validated PDF. Never submit.
    inspect_only opens and analyzes the landing page without clicking Apply, filling fields,
    uploading files, or advancing any application step.
    """
    profile=load_profile();identity=_identity(profile);url=item.get("url")
    result={"external_id":item.get("external_id"),"url":url,"status":"INSPECTING" if inspect_only else "FILLING","inspect_only":inspect_only,"filled":[],"unresolved_required":[],"blockers":[],"submitted":False,"navigation":None}
    resume=_resolve_resume(item.get("resume_path"))
    if resume is None:
        return {**result,"status":"MANUAL_ACTION_REQUIRED","reason":"Validated resume file is missing","expected_resume_path":item.get("resume_path")}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=headless);page=browser.new_page()
        try:
            page.goto(url,wait_until="domcontentloaded",timeout=60000)
            result["application_analysis"]={"landing":_application_preflight(page)}
            if inspect_only:
                result["status"]="MANUAL_ACTION_REQUIRED" if result["application_analysis"]["landing"]["blocker_detected"] else "INSPECTED_NO_CHANGES"
                result["reason"]="Inspection only; no fields filled, files uploaded, or application actions clicked."
                return result
            provider=(item.get("ats_provider") or "").lower()
            if provider=="workday":
                result["navigation"]=_workday_enter_application(page)
                _wait_for_application_controls(page,15000)
                result["application_analysis"]["after_apply_entry"]=_application_preflight(page)
            else:
                result["navigation"]=enter_application(page,provider)
                result["application_analysis"]["after_apply_entry"]=analyze_application(page)
                if result["navigation"].get("blocker"):
                    result["blockers"].append(result["navigation"]["blocker"])
                    result["status"]="MANUAL_ACTION_REQUIRED"
                    result["reason"]="Application entry is blocked by CAPTCHA/MFA/verification."
                    return result
                if not result["navigation"].get("entered"):
                    result["status"]="MANUAL_ACTION_REQUIRED"
                    result["reason"]=result["navigation"].get("reason") or "Could not reach application form safely."
                    return result
            # Dice presents an email-only first gate. Advance it before looking for
            # the password/account form; otherwise the email field is mistaken for the
            # application itself and the run incorrectly searches for final Submit.
            dice_gate=_dice_email_continue(page,result)
            result["dice_email_gate"]=dice_gate
            # Workday tenants such as CVS first show Google/LinkedIn/email choices.
            # Open the deterministic email path before attempting credentials.
            if provider=="workday":
                result["workday_email_auth_entry"]=_workday_open_email_auth(page)
            # Handle ordinary ATS login/account creation automatically using local env credentials.
            auth=_auth_action(page,result)
            result["authentication"]=auth
            if auth.get("handled"):
                page.wait_for_timeout(1800)
                try: page.wait_for_load_state("domcontentloaded",timeout=8000)
                except Exception: pass
                result["application_analysis"]["after_auth"]=analyze_application(page)
            body=page.locator("body").inner_text(timeout=10000)
            if BLOCKER_RE.search(body) or (result.get("navigation") or {}).get("blocker"):
                if wait_for_human_seconds>0 and not headless:
                    result["status"]="WAITING_FOR_HUMAN_VERIFICATION"
                    result["human_verification_wait_seconds"]=wait_for_human_seconds
                    elapsed=0
                    while elapsed<wait_for_human_seconds:
                        page.wait_for_timeout(1000);elapsed+=1
                        check=analyze_application(page)
                        if not check.get("blocker_detected"):
                            result["human_verification_cleared"]=True
                            result["blockers"]=[]
                            result["navigation_after_human"]=check
                            break
                    else:
                        result["blockers"].append("CAPTCHA/MFA/verification challenge detected")
                        result["status"]="MANUAL_ACTION_REQUIRED"
                        result["reason"]="Human verification was not completed before timeout."
                        return result
                else:
                    result["blockers"].append("CAPTCHA/MFA/verification challenge detected");result["status"]="MANUAL_ACTION_REQUIRED";return result
            if provider=="dice":
                result["dice_resume_upload"]=_dice_resume_upload(page,resume,result)
                if result["dice_resume_upload"].get("handled") and not result["dice_resume_upload"].get("verified"):
                    result["unresolved_required"]=["Dice tailored resume replacement could not be verified"]
                    result["status"]="MANUAL_ACTION_REQUIRED"
                    result["reason"]="Tailored resume was not verified in the Dice Resume section; refusing to advance."
                    return result
            if (item.get("ats_provider") or "").lower()=="workday":
                result["workday_steps"]=_workday_steps(page,item,identity,resume,result,profile)
                result["unresolved_required"]=sorted(set(q for s in result["workday_steps"] for q in s.get("unresolved_required",[])))
            else:
                result["generic_steps"]=_generic_steps(page,item,identity,resume,result,profile)
                result["unresolved_required"]=sorted(set(
                    q for s in result["generic_steps"] for q in s.get("unresolved_required",[])
                ))
            # A page with zero mapped fields is not a successful autofill. Workday
            # commonly lands on a job-description/sign-in step before its application form.
            if result["blockers"]:
                result["status"]="MANUAL_ACTION_REQUIRED"
                result["reason"]="Application has a validation, CAPTCHA/MFA, or verification blocker."
            elif not result["filled"]:
                result["status"]="MANUAL_ACTION_REQUIRED"
                result["reason"]="No application form fields were mapped; application form may require an Apply/sign-in step."
            else:
                result["status"]="MANUAL_ACTION_REQUIRED" if result["unresolved_required"] else "AUTOFILLED_REVIEW_REQUIRED"
                if allow_submit and not result["unresolved_required"] and not result["blockers"]:
                    final=_find_final_submit(page)
                    if final:
                        try:
                            result["final_submit_action"]=final[3]
                            result["final_submit_scope_url"]=final[4]
                            # Persist a terminal uncertainty marker immediately before
                            # the irreversible final click. If the process dies after
                            # this point, the scheduler must require manual confirmation
                            # instead of replaying and risking a duplicate application.
                            if before_submit is not None:
                                before_submit(item,{
                                    "external_id":item.get("external_id"),
                                    "url":page.url,
                                    "final_submit_action":final[3],
                                    "final_submit_scope_url":final[4],
                                })
                            result["submission_attempted"]=True
                            final[2].click(timeout=5000)
                            confirmation=_submission_confirmation(page)
                            result["submission_confirmation"]=confirmation
                            validation_errors=_visible_validation_errors(page)
                            if validation_errors:
                                result["post_submit_validation_errors"]=validation_errors
                            result["submitted"]=bool(confirmation["confirmed"])
                            result["status"]="SUBMITTED" if confirmation["confirmed"] else "SUBMISSION_UNCONFIRMED"
                            if not confirmation["confirmed"]:
                                result["reason"]=(
                                    "Final submit was rejected by ATS validation."
                                    if validation_errors else
                                    "Final submit was clicked, but no verifiable ATS confirmation was detected."
                                )
                        except Exception as exc:
                            result["status"]="SUBMISSION_UNCONFIRMED"
                            result["reason"]=str(exc)
                    else:
                        result["status"]="MANUAL_ACTION_REQUIRED"
                        result["reason"]="Submission authorized, but no unambiguous final-submit control was found."
        except Exception as exc:
            result["status"]="MANUAL_ACTION_REQUIRED";result["reason"]=str(exc)
        finally:
            if not headless and review_seconds>0:
                print(f"Browser will stay open for {review_seconds} seconds for review...")
                page.wait_for_timeout(review_seconds*1000)
            browser.close()
    return result

def run(queue_path="generated/application_queue.json",output="generated/application_autofill.json",limit=None,headless=True,review_seconds=0,inspect_only=False,wait_for_human_seconds=0,allow_submit=False,before_submit=None):
    rows=json.loads(Path(queue_path).read_text(encoding="utf-8"));results=[]
    for item in rows:
        if item.get("status")!="READY_FOR_ATS_ADAPTER":continue
        if limit is not None and len(results)>=limit:break
        results.append(autofill(item,headless,review_seconds,inspect_only,wait_for_human_seconds,allow_submit,before_submit))
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(results,indent=2),encoding="utf-8");return results

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--queue",default="generated/application_queue.json");ap.add_argument("--output",default="generated/application_autofill.json");ap.add_argument("--limit",type=int);ap.add_argument("--headed",action="store_true");ap.add_argument("--review-seconds",type=int,default=0);ap.add_argument("--inspect-only",action="store_true",help="Open and analyze the landing page without filling, uploading, clicking Apply, advancing, or submitting.");ap.add_argument("--wait-for-human-seconds",type=int,default=0,help="In headed mode, keep the same browser session open for CAPTCHA/MFA completion, then resume automatically.");ap.add_argument("--allow-submit",action="store_true",help="Explicitly authorize clicking an unambiguous final application submit control. Success is recorded only after confirmation evidence.");a=ap.parse_args()
    rows=run(a.queue,a.output,a.limit,not a.headed,a.review_seconds,a.inspect_only,a.wait_for_human_seconds,a.allow_submit);print(json.dumps({"processed":len(rows),"autofilled_review_required":sum(x["status"]=="AUTOFILLED_REVIEW_REQUIRED" for x in rows),"manual_action":sum(x["status"]=="MANUAL_ACTION_REQUIRED" for x in rows),"output":a.output},indent=2))
