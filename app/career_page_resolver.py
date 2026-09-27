from __future__ import annotations
import json,re
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
from app.source_registry import detect_ats

UA={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"}
CAREER_WORDS=("careers","career","jobs","join us","join-us","join our team","work with us","work here","opportunities","open positions","job openings")
FALLBACK_PATHS=("careers","jobs","careers/jobs","company/careers","about/careers","about-us/careers","join-us","join-our-team","work-with-us","work-here","opportunities","open-positions","job-openings","employment","en/careers","en-us/careers","us/en/careers","search-jobs","job-search")
URL_ATTRS=("href","src","action","data-url","data-href","data-src")

def _get(url,timeout=15):
    with urlopen(Request(url,headers=UA),timeout=timeout) as r:
        return r.geturl(),r.read().decode("utf-8","ignore")

def _urls(body,base):
    found=[]
    attrs="|".join(re.escape(x) for x in URL_ATTRS)
    for _,link in re.findall(rf'({attrs})=["\']([^"\']+)["\']',body,re.I):
        if link and not link.lower().startswith(("javascript:","mailto:","tel:","#")):
            found.append(urljoin(base,link))
    # JSON/JS frequently contains escaped ATS URLs outside HTML attributes.
    scan_body=body.replace("\\/","/")
    for link in re.findall(r"""https?://[^\s"\'<>]+""",scan_body,re.I):
        found.append(link.replace("\\/","/"))
    return list(dict.fromkeys(found))

def _ats_from_page(final,body):
    provider,ident=detect_ats(final)
    if provider:return final,provider,ident
    hits=[]
    for link in _urls(body,final):
        p,i=detect_ats(link)
        if p:hits.append((link,p,i))
    if hits:
        # Prefer navigable job/board URLs over static assets.
        hits.sort(key=lambda x:(bool(re.search(r'\.(?:js|css|png|svg|jpg)(?:\?|$)',x[0],re.I)),len(x[0])))
        return hits[0]
    return None

def _jobposting_evidence(body):
    low=body.lower()
    return ('"@type"' in low and "jobposting" in low) or any(x in low for x in ("job opening","open positions","search jobs","view jobs"))

def _career_page_evidence(url,body):
    """Recognize a real first-party recruiting destination without pretending it is an ATS."""
    path=urlparse(url).path.lower()
    low=re.sub(r"<[^>]+>"," ",body).lower()
    path_hit=any(x in path for x in ("/careers","/career","/jobs","/employment","/opportunities","/join-us","/work-with-us"))
    recruiting_hit=any(x in low[:120000] for x in ("careers","join our team","job openings","open positions","search jobs","view jobs","employment opportunities"))
    return path_hit and recruiting_hit

def _jsonld_urls(body,base):
    out=[]
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',body,re.I|re.S):
        try:
            data=json.loads(raw)
        except Exception:
            continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            obj=stack.pop()
            if isinstance(obj,list):stack.extend(obj);continue
            if not isinstance(obj,dict):continue
            typ=str(obj.get("@type") or "").lower()
            if "jobposting" in typ:
                for key in ("url","sameAs"):
                    val=obj.get(key)
                    if isinstance(val,str):out.append(urljoin(base,val))
                org=obj.get("hiringOrganization")
                if isinstance(org,dict):
                    for key in ("url","sameAs"):
                        val=org.get(key)
                        if isinstance(val,str):out.append(urljoin(base,val))
            for val in obj.values():
                if isinstance(val,(dict,list)):stack.append(val)
    return list(dict.fromkeys(out))

def _sitemap_candidates(root,body,timeout):
    out=[]
    # robots.txt can advertise non-standard sitemap locations.
    try:
        _,robots=_get(urljoin(root,"robots.txt"),timeout)
        for u in re.findall(r'^\s*Sitemap:\s*(\S+)',robots,re.I|re.M):out.append(u.strip())
    except Exception:pass
    out += [urljoin(root,"sitemap.xml"),urljoin(root,"sitemap_index.xml")]
    pages=[]
    for sm in list(dict.fromkeys(out))[:4]:
        try:
            _,xml=_get(sm,timeout)
        except Exception:
            continue
        locs=re.findall(r'<loc>\s*([^<]+)\s*</loc>',xml,re.I)
        for u in locs[:5000]:
            low=u.lower()
            if any(w.replace(" ","-") in low or w.replace(" ","") in low for w in CAREER_WORDS):
                pages.append(u.strip())
        # One bounded level of sitemap indexes.
        for child in locs[:100]:
            if "sitemap" not in child.lower():continue
            try:
                _,xml2=_get(child,timeout)
                for u in re.findall(r'<loc>\s*([^<]+)\s*</loc>',xml2,re.I)[:5000]:
                    low=u.lower()
                    if any(w.replace(" ","-") in low or w.replace(" ","") in low for w in CAREER_WORDS):
                        pages.append(u.strip())
            except Exception:continue
    return list(dict.fromkeys(pages))[:40]

def resolve(official_domain,timeout=15):
    """Resolve an evidence-backed employer domain to an executable public career source."""
    if not official_domain:return None
    root=official_domain if "://" in official_domain else "https://"+official_domain
    root=root.rstrip("/")+"/"
    candidates=[];home_body=""
    try:
        final,home_body=_get(root,timeout)
        root=final.rstrip("/")+"/"
        for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',home_body,re.I|re.S):
            text=re.sub("<[^>]+>"," ",label).lower()
            if any(w in text or w in href.lower() for w in CAREER_WORDS):
                candidates.append(urljoin(final,href))
        candidates += _jsonld_urls(home_body,final)
        hit=_ats_from_page(final,home_body)
        if hit and any(w in hit[0].lower() for w in ("job","career")):
            u,p,i=hit
            return {"careers_url":u,"ats_provider":p,"ats_identifier":i}
    except Exception:pass

    candidates += [urljoin(root,p) for p in FALLBACK_PATHS]
    # Common first-party career subdomains are evidence-preserving because they
    # remain under the already verified corporate registrable domain.
    parsed_root=urlparse(root)
    host=parsed_root.netloc.lower()
    base_host=host[4:] if host.startswith("www.") else host
    candidates += [f"https://careers.{base_host}/",f"https://jobs.{base_host}/"]
    candidates += _sitemap_candidates(root,home_body,timeout)
    seen=set()
    for url in candidates:
        if url in seen:continue
        seen.add(url)
        try:
            final,body=_get(url,timeout)
            for structured in _jsonld_urls(body,final):
                hit=detect_ats(structured)
                if hit[0]:
                    return {"careers_url":structured,"ats_provider":hit[0],"ats_identifier":hit[1]}
            hit=_ats_from_page(final,body)
            if hit:
                u,p,i=hit
                # Embedded ATS scripts prove the provider, but a CDN/static asset
                # is not a navigable job board. Keep the verified employer career
                # page as the executable URL in that case.
                career_url = final if re.search(r'\.(?:js|css|png|svg|jpg)(?:\?|$)',u,re.I) else u
                return {"careers_url":career_url,"ats_provider":p,"ats_identifier":i}
            if _jobposting_evidence(body) or _career_page_evidence(final,body):
                return {"careers_url":final,"ats_provider":"career_site","ats_identifier":urlparse(final).netloc}
        except Exception:continue
    return None
