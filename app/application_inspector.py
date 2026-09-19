from __future__ import annotations
import argparse,json,re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

TEXT_FIELDS={
 "first name":"first_name","last name":"last_name","full name":"full_name","email":"email","phone":"phone",
 "linkedin":"linkedin","linkedin url":"linkedin",
}
BLOCKER_RE=re.compile(r"captcha|recaptcha|hcaptcha|verification code|two[- ]factor|\bmfa\b",re.I)

def _provider(url):
    host=urlparse(url or "").netloc.lower()
    for token,name in (("greenhouse","greenhouse"),("lever","lever"),("ashby","ashby"),("myworkdayjobs","workday"),("smartrecruiters","smartrecruiters"),("icims","icims"),("jobvite","jobvite"),("dice.com","dice")):
        if token in host:return name
    return "unknown"

def inspect_application(item:dict,headless=True)->dict:
    """Open an application safely, detect fields/blockers, and never submit."""
    url=item.get("url");result={"external_id":item.get("external_id"),"url":url,"ats_provider":item.get("ats_provider") or _provider(url),"status":"INSPECTING","fields":[],"blockers":[]}
    if not url:return {**result,"status":"MANUAL_ACTION_REQUIRED","reason":"Missing application URL"}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=headless);page=browser.new_page()
        try:
            page.goto(url,wait_until="domcontentloaded",timeout=45000)
            body=page.locator("body").inner_text(timeout=10000)
            if BLOCKER_RE.search(body):result["blockers"].append("CAPTCHA/MFA/verification challenge detected")
            controls=page.locator("input, textarea, select")
            for i in range(min(controls.count(),200)):
                el=controls.nth(i)
                typ=(el.get_attribute("type") or el.evaluate("(e)=>e.tagName")).lower()
                if typ in ("hidden","submit","button"):continue
                label=el.get_attribute("aria-label") or el.get_attribute("placeholder") or el.get_attribute("name") or el.get_attribute("id") or ""
                result["fields"].append({"label":label,"type":typ,"required":el.get_attribute("required") is not None})
            actions=[]
            for i in range(min(page.locator("a, button").count(),200)):
                el=page.locator("a, button").nth(i)
                txt=(el.inner_text(timeout=1000) or "").strip()
                if re.search(r"apply|application",txt,re.I): actions.append({"text":txt,"href":el.get_attribute("href")})
            result["actions"]=actions;result["final_url"]=page.url;result["body_excerpt"]=body[:5000]
            result["status"]="MANUAL_ACTION_REQUIRED" if result["blockers"] else "INSPECTED_READY_FOR_MAPPING"
        except Exception as exc:
            result["status"]="MANUAL_ACTION_REQUIRED";result["reason"]=str(exc)
        finally:browser.close()
    return result

def inspect_url(url:str,headless=True,external_id="direct-inspection")->dict:
    """Inspect a direct job/application URL without requiring a generated queue."""
    return inspect_application({"external_id":external_id,"url":url,"ats_provider":_provider(url)},headless=headless)


def inspect_apply_route(url:str,headless=True,external_id="direct-inspection")->dict:
    """Follow only an href-backed Apply link, then inspect without filling or submitting."""
    result=inspect_url(url,headless=headless,external_id=external_id)
    if result.get("status")=="MANUAL_ACTION_REQUIRED": return result
    candidates=[a for a in result.get("actions",[]) if re.search(r"apply",a.get("text") or "",re.I) and a.get("href")]
    if not candidates:
        result["status"]="MANUAL_ACTION_REQUIRED";result["reason"]="No safe href-backed Apply link found; no click performed.";return result
    from urllib.parse import urljoin
    chosen=candidates[0];destination=urljoin(result.get("final_url") or url,chosen["href"])
    routed=inspect_url(destination,headless=headless,external_id=external_id)
    result["apply_route"]={"entry_text":chosen["text"],"destination":destination,"inspection":routed}
    result["status"]="APPLY_ROUTE_INSPECTED" if routed.get("status")!="MANUAL_ACTION_REQUIRED" else "MANUAL_ACTION_REQUIRED"
    return result

def run(queue_path="generated/application_queue.json",output="generated/application_inspection.json",limit=None,headless=True):
    rows=json.loads(Path(queue_path).read_text(encoding="utf-8"));out=[]
    for item in rows:
        if item.get("status")!="READY_FOR_ATS_ADAPTER":continue
        if limit is not None and len(out)>=limit:break
        out.append(inspect_application(item,headless=headless))
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,indent=2),encoding="utf-8");return out

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--queue",default="generated/application_queue.json")
    ap.add_argument("--url")
    ap.add_argument("--output",default="generated/application_inspection.json")\n    ap.add_argument("--inspect-apply-route",action="store_true")
    ap.add_argument("--limit",type=int)
    ap.add_argument("--headed",action="store_true")
    a=ap.parse_args()
    if a.url:
        rows=[inspect_apply_route(a.url,not a.headed) if a.inspect_apply_route else inspect_url(a.url,not a.headed)]
        p=Path(a.output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rows,indent=2),encoding="utf-8")
    else:
        rows=run(a.queue,a.output,a.limit,not a.headed)
    print(json.dumps({"inspected":len(rows),"manual_action":sum(x["status"]=="MANUAL_ACTION_REQUIRED" for x in rows),"ready_for_mapping":sum(x["status"]=="INSPECTED_READY_FOR_MAPPING" for x in rows),"output":a.output},indent=2))
