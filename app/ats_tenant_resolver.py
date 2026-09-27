from __future__ import annotations
"""Evidence-backed ATS board discovery from employer identity.

This is a fallback for employers that do not yet have a verified corporate
domain. Candidate slugs are never accepted merely because an endpoint exists:
the ATS board must expose an organization name that matches the employer.
"""
import html,json,re
from urllib.parse import quote,quote_plus,urlparse,parse_qs,unquote
from urllib.request import Request,urlopen
from app.source_registry import detect_ats

UA={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"}
STOP={"inc","incorporated","corp","corporation","company","co","llc","ltd","limited","plc",
      "group","holdings","holding","the","and","of","usa","us"}

def _tokens(value):
    return [x.lower() for x in re.findall(r"[A-Za-z0-9]+",value or "")
            if len(x)>=2 and x.lower() not in STOP]

def _matches(expected,observed):
    a=_tokens(expected);b=set(_tokens(observed))
    if not a or not b:return False
    needed=1 if len(a)==1 else min(2,len(a))
    return sum(x in b for x in a)>=needed

def _slugs(company):
    t=_tokens(company)
    if not t:return []
    vals=["".join(t),"-".join(t)]
    if len(t)>1:vals += [t[0], "".join(x[0] for x in t if x)]
    return list(dict.fromkeys(x for x in vals if 2<=len(x)<=80))[:4]

def _json(url,timeout):
    with urlopen(Request(url,headers=UA),timeout=timeout) as r:
        return json.load(r)

def _unwrap(raw):
    raw=html.unescape(raw).replace("\\/","/")
    if raw.startswith("//"):raw="https:"+raw
    if "duckduckgo.com/l/?" in raw:
        q=parse_qs(urlparse(raw).query)
        raw=unquote((q.get("uddg") or [""])[0])
    return raw if raw.startswith(("http://","https://")) else None

def _hosted_search_candidates(company,timeout=6):
    """Discover ATS URLs from public search; URLs are candidates, never evidence."""
    q=quote_plus(f'"{company}" careers jobs')
    endpoints=[
        "https://html.duckduckgo.com/html/?q="+q,
        "https://www.bing.com/search?q="+q,
    ]
    out=[]
    for endpoint in endpoints:
        try:
            with urlopen(Request(endpoint,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"en-US,en;q=0.9"}),timeout=timeout) as r:
                body=r.read(500000).decode("utf-8","ignore")
        except Exception:
            continue
        raw_links=re.findall(r'href=["\\']([^"\\']+)["\\']',body,re.I)
        raw_links+=re.findall(r'https?://[^"&<>\\s]+',body,re.I)
        for raw in raw_links:
            url=_unwrap(raw)
            if not url:continue
            provider,identifier=detect_ats(url)
            if provider and identifier:
                key=(provider,identifier,url)
                if key not in out:out.append(key)
        if out:break
    return out[:12]

def _verify_hosted_page(company,url,provider,identifier,timeout=6):
    try:
        with urlopen(Request(url,headers=UA),timeout=timeout) as r:
            final=r.geturl();body=r.read(300000).decode("utf-8","ignore")
    except Exception:
        return None
    title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
    observed=re.sub(r"<[^>]+>"," ",html.unescape(title.group(1))) if title else ""
    meta=" ".join(re.findall(r'<meta[^>]+(?:content|value)=["\\']([^"\\']+)["\\']',body,re.I))
    if not (_matches(company,observed) or _matches(company,meta)):
        return None
    p,i=detect_ats(final)
    return {"careers_url":final,"ats_provider":p or provider,"ats_identifier":i or identifier,
            "ats_evidence":"public_search_plus_hosted_board_identity"}

def resolve(company,timeout=6):
    """Return a verified public ATS board for a company name, or None."""
    # Search can reveal non-obvious tenant identifiers and long-tail ATS families.
    # Acceptance still requires identity evidence on the ATS-hosted destination.
    for provider,identifier,url in _hosted_search_candidates(company,timeout):
        hit=_verify_hosted_page(company,url,provider,identifier,timeout)
        if hit:return hit
    for slug in _slugs(company):
        # Greenhouse exposes the board's organization name directly.
        try:
            data=_json(f"https://boards-api.greenhouse.io/v1/boards/{quote(slug)}",timeout)
            name=str(data.get("name") or "")
            if _matches(company,name):
                return {"careers_url":f"https://boards.greenhouse.io/{slug}",
                        "ats_provider":"greenhouse","ats_identifier":slug,
                        "ats_evidence":"greenhouse_public_board_name"}
        except Exception:pass

        # Ashby does not expose an organization-name field in the posting API,
        # so verify identity against its hosted board HTML title/content.
        try:
            url=f"https://jobs.ashbyhq.com/{quote(slug)}"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"ashby","ats_identifier":slug,
                        "ats_evidence":"ashby_hosted_board_identity"}
        except Exception:pass

        # Lever hosted boards are public; verify the company identity in the
        # board metadata/title rather than accepting a guessed slug.
        try:
            url=f"https://jobs.lever.co/{quote(slug)}"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"lever","ats_identifier":slug,
                        "ats_evidence":"lever_hosted_board_identity"}
        except Exception:pass

        # SmartRecruiters identifiers are visible in the public career-site URL.
        # Verify identity on that hosted career page before learning the tenant.
        try:
            url=f"https://careers.smartrecruiters.com/{quote(slug)}"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"smartrecruiters","ats_identifier":slug,
                        "ats_evidence":"smartrecruiters_hosted_board_identity"}
        except Exception:pass
        # Workable hosted boards expose the employer identity in page metadata.
        try:
            url=f"https://apply.workable.com/{quote(slug)}/"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"workable","ats_identifier":slug,
                        "ats_evidence":"workable_hosted_board_identity"}
        except Exception:pass

        # Recruitee commonly uses employer-specific subdomains.
        try:
            url=f"https://{quote(slug)}.recruitee.com/"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"recruitee","ats_identifier":slug,
                        "ats_evidence":"recruitee_hosted_board_identity"}
        except Exception:pass

        # Teamtailor also uses employer-specific hosted career subdomains.
        try:
            url=f"https://{quote(slug)}.teamtailor.com/"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"teamtailor","ats_identifier":slug,
                        "ats_evidence":"teamtailor_hosted_board_identity"}
        except Exception:pass

        # BambooHR tenants expose a public careers page on a tenant subdomain.
        try:
            url=f"https://{quote(slug)}.bamboohr.com/careers"
            with urlopen(Request(url,headers=UA),timeout=timeout) as r:
                body=r.read(250000).decode("utf-8","ignore")
            title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
            observed=re.sub(r"<[^>]+>"," ",title.group(1)) if title else ""
            if _matches(company,observed):
                return {"careers_url":url,"ats_provider":"bamboohr","ats_identifier":slug,
                        "ats_evidence":"bamboohr_hosted_board_identity"}
        except Exception:pass
    return None
