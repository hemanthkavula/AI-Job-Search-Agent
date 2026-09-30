from __future__ import annotations
import html,json,re
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
UA={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/json,*/*"}
def _get(u,t=25):
    with urlopen(Request(u,headers=UA),timeout=t) as r:return r.read().decode("utf-8","replace")
def _plain(v):return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(str(v or "")))).strip()
def _posts(b):
    out=[]
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',b,re.I|re.S):
        try:d=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        stack=d if isinstance(d,list) else [d]
        while stack:
            n=stack.pop()
            if isinstance(n,dict):
                if n.get("@type")=="JobPosting":out.append(n)
                if isinstance(n.get("@graph"),list):stack.extend(n["@graph"])
    return out
def fetch_jobs(company:str,search_url:str,timeout:int=25)->list[dict]:
    """Collect all public Jobvite postings and defer qualification downstream."""
    body=_get(search_url,timeout);candidates=[(search_url,j) for j in _posts(body)];links=[];seen_links=set()
    for h in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
        u=urljoin(search_url,html.unescape(h));lo=u.lower()
        if any(x in lo for x in ("/job/","/jobs/","jobdetail","job-details","jobid=","requisition")) and u not in seen_links:
            seen_links.add(u);links.append(u)
    for u in links:
        try:candidates.extend((u,j) for j in _posts(_get(u,timeout)))
        except Exception:pass
    tenant=urlparse(search_url).netloc;out=[];ids=set()
    for page,j in candidates:
        title=_plain(j.get("title"));desc=_plain(j.get("description"))
        ident=j.get("identifier") or page
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or page
        ident=str(ident)
        if ident in ids:continue
        ids.add(ident);url=str(j.get("url") or page)
        out.append({"external_id":f"jobvite:{tenant}:{ident}","source":"jobvite","company_key":company,"title":title,"location":None,"url":url,"original_url":url,"ats_provider":"jobvite","ats_identifier":tenant,"job_id":ident,"description":desc,"description_complete":bool(desc),"posted_on":j.get("datePosted"),"updated_at":j.get("datePosted"),"valid_through":j.get("validThrough")})
    print(f"Jobvite / {company}: {len(out)} jobs discovered from {len(links)} detail links",flush=True)
    return out
