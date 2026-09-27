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
    body=_get(search_url,timeout); candidates=[(search_url,j) for j in _posts(body)]; seen_links=set()
    # Modern Dayforce career sites load jobs client-side via this contract.
    try:
        m=re.search(r'<script[^>]+id=["\\\']__NEXT_DATA__["\\\'][^>]*>(.*?)</script>',body,re.I|re.S)
        nd=json.loads(html.unescape(m.group(1).strip())) if m else {}
        pp=(nd.get("props") or {}).get("pageProps") or {}
        queries=((pp.get("dehydratedState") or {}).get("queries") or [])
        site={}
        for q in queries:
            if isinstance(q,dict) and isinstance((q.get("state") or {}).get("data"),dict):
                d=(q.get("state") or {}).get("data")
                if d.get("clientNamespace") and d.get("jobBoardId") is not None: site=d;break
        ns=site.get("clientNamespace")
        board=site.get("jobBoardCode") or ((nd.get("query") or {}).get("careerSiteXRefCode"))
        culture=site.get("cultureCode") or "en-US"
        if ns and board:
            api="https://jobs.dayforcehcm.com/api/geo/"+str(ns)+"/jobposting/search"
            for start in range(0,500,25):
                payload={"clientNamespace":ns,"jobBoardCode":board,"cultureCode":culture,"paginationStart":start}
                data=_post_json(api,payload,timeout)
                rows=data.get("jobPostings") if isinstance(data,dict) else None
                if not isinstance(rows,list) or not rows: break
                for j in rows:
                    if not isinstance(j,dict): continue
                    jid=j.get("jobPostingId")
                    page=urljoin("https://jobs.dayforcehcm.com/",f"/{culture}/{ns}/{board}/jobs/{jid}") if jid else search_url
                    candidates.append((page,{"@type":"JobPosting","title":j.get("jobTitle"),"description":(j.get("jobPostingContent") or {}).get("jobDescription") if isinstance(j.get("jobPostingContent"),dict) else j.get("description"),"identifier":jid,"url":page,"datePosted":j.get("postingStartTimestampUTC"),"_dayforce":j}))
                if len(rows)<25 or (isinstance(data.get("maxCount"),int) and start+len(rows)>=data["maxCount"]): break
    except Exception:
        pass
    for h in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
        u=urljoin(search_url,html.unescape(h));lo=u.lower()
        if not any(x in lo for x in ("/job/","/jobs/","jobdetail","job-details","posting")) or u in seen_links:continue
        seen_links.add(u)
        try:candidates.extend((u,j) for j in _posts(_get(u,timeout)))
        except Exception:pass
        if len(seen_links)>=300:break
    tenant=urlparse(search_url).netloc;out=[];ids=set()
    for page,j in candidates:
        title=_plain(j.get("title"));desc=_plain(j.get("description"));hay=(title+" "+desc[:3000]).lower()
        if not any(x in hay for x in ("data engineer","data engineering","data platform engineer","data infrastructure engineer","data integration engineer","etl engineer","analytics engineer","big data engineer")):continue
        ident=j.get("identifier") or page
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or page
        ident=str(ident)
        if ident in ids:continue
        ids.add(ident);url=str(j.get("url") or page)
        loc=j.get("jobLocation");location=None
        if isinstance(loc,dict) and isinstance(loc.get("address"),dict):
            a=loc["address"];location=", ".join(str(a.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if a.get(k)) or None
        out.append({"external_id":f"dayforce:{tenant}:{ident}","source":"dayforce","company_key":company,"title":title,"location":location,"url":url,"original_url":url,"ats_provider":"dayforce","ats_identifier":tenant,"job_id":ident,"description":desc,"description_complete":bool(desc),"updated_at":j.get("datePosted") or j.get("validThrough")})
    return out
