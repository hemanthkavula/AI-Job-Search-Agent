from __future__ import annotations
import html,json,re
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
UA={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/json,*/*"}

def _get(u,t=25):
    with urlopen(Request(u,headers=UA),timeout=t) as r:return r.read().decode("utf-8","replace")
def _post_json(u,payload,t=25):
    data=json.dumps(payload).encode("utf-8")
    req=Request(u,data=data,headers={**UA,"Content-Type":"application/json"})
    with urlopen(req,timeout=t) as r:return json.loads(r.read().decode("utf-8","replace"))
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

def fetch_jobs(company:str,search_url:str,timeout:int=25,max_api_pages:int|None=None,max_fallback_links:int|None=None)->list[dict]:
    """Fetch all public Dayforce postings visible from API/page frontiers.

    Source discovery maximizes recall. Job-family and candidate eligibility are
    evaluated centrally downstream. Optional ceilings are emergency safeguards
    only and are surfaced as TRUNCATED.
    """
    body=_get(search_url,timeout);candidates=[(search_url,j) for j in _posts(body)];seen_links=set();api_pages=0;truncated=[]
    try:
        m=re.search(r'<script[^>]+id=["\\\']__NEXT_DATA__["\\\'][^>]*>(.*?)</script>',body,re.I|re.S)
        nd=json.loads(html.unescape(m.group(1).strip())) if m else {};pp=(nd.get("props") or {}).get("pageProps") or {};queries=((pp.get("dehydratedState") or {}).get("queries") or []);site={}
        for q in queries:
            if isinstance(q,dict) and isinstance((q.get("state") or {}).get("data"),dict):
                d=(q.get("state") or {}).get("data")
                if d.get("clientNamespace") and d.get("jobBoardId") is not None:site=d;break
        ns=site.get("clientNamespace");board=site.get("jobBoardCode") or ((nd.get("query") or {}).get("careerSiteXRefCode"));culture=site.get("cultureCode") or "en-US"
        if ns and board:
            api="https://jobs.dayforcehcm.com/api/geo/"+str(ns)+"/jobposting/search";start=0;page_size=25
            while True:
                if max_api_pages is not None and api_pages>=max_api_pages:truncated.append("api_pages");break
                payload={"clientNamespace":ns,"jobBoardCode":board,"cultureCode":culture,"paginationStart":start}
                data=_post_json(api,payload,timeout);api_pages+=1;rows=data.get("jobPostings") if isinstance(data,dict) else None
                if not isinstance(rows,list) or not rows:break
                for j in rows:
                    if not isinstance(j,dict):continue
                    jid=j.get("jobPostingId");page=urljoin("https://jobs.dayforcehcm.com/",f"/{culture}/{ns}/{board}/jobs/{jid}") if jid else search_url
                    candidates.append((page,{"@type":"JobPosting","title":j.get("jobTitle"),"description":(j.get("jobPostingContent") or {}).get("jobDescription") if isinstance(j.get("jobPostingContent"),dict) else j.get("description"),"identifier":jid,"url":page,"datePosted":j.get("postingStartTimestampUTC"),"_dayforce":j}))
                start+=len(rows);max_count=data.get("maxCount") if isinstance(data,dict) else None
                if len(rows)<page_size or (isinstance(max_count,int) and start>=max_count):break
    except Exception as exc:
        print(f"Dayforce / {company}: structured API fallback reason={type(exc).__name__}:{exc}",flush=True)
    for h in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
        u=urljoin(search_url,html.unescape(h));lo=u.lower()
        if not any(x in lo for x in ("/job/","/jobs/","jobdetail","job-details","posting")) or u in seen_links:continue
        if max_fallback_links is not None and len(seen_links)>=max_fallback_links:truncated.append("fallback_links");break
        seen_links.add(u)
        try:candidates.extend((u,j) for j in _posts(_get(u,timeout)))
        except Exception:pass
    tenant=urlparse(search_url).netloc;out=[];ids=set()
    for page,j in candidates:
        title=_plain(j.get("title"));desc=_plain(j.get("description"))
        ident=j.get("identifier") or page
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or page
        ident=str(ident)
        if ident in ids:continue
        ids.add(ident);url=str(j.get("url") or page);loc=j.get("jobLocation");location=None
        if isinstance(loc,dict) and isinstance(loc.get("address"),dict):
            a=loc["address"];location=", ".join(str(a.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if a.get(k)) or None
        out.append({"external_id":f"dayforce:{tenant}:{ident}","source":"dayforce","company_key":company,"title":title,"location":location,"url":url,"original_url":url,"ats_provider":"dayforce","ats_identifier":tenant,"job_id":ident,"description":desc,"description_complete":bool(desc),"posted_on":j.get("datePosted"),"updated_at":j.get("datePosted"),"valid_through":j.get("validThrough")})
    state="TRUNCATED" if truncated else "EXHAUSTED_OR_PAGE_LINK_FRONTIER"
    print(f"Dayforce / {company}: {len(out)} jobs discovered, {api_pages} API pages, {len(seen_links)} fallback links, pagination={state}"+(f", reasons={','.join(sorted(set(truncated)))}" if truncated else ""),flush=True)
    return out
