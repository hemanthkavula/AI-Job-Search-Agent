from __future__ import annotations
"""Resolve company identities to verified official corporate domains.

Candidates may be discovered from public search, but are accepted only after
first-party page evidence ties the candidate site back to the employer.
"""
import html,json,re
from urllib.parse import urlparse,quote_plus,unquote,urljoin,parse_qs
from urllib.request import Request,urlopen

UA={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"}
BLOCKED=("google.","bing.com","duckduckgo.com","yahoo.com","linkedin.com","facebook.com","instagram.com",
         "x.com","twitter.com","wikipedia.org","crunchbase.com","bloomberg.com","indeed.com",
         "glassdoor.com","ziprecruiter.com","dice.com","monster.com","builtin.com","wellfound.com",
         "greenhouse.io","lever.co","ashbyhq.com","workdayjobs.com","myworkdayjobs.com",
         "smartrecruiters.com","icims.com","jobvite.com",".gov")

def _host(url):
    try:
        h=urlparse(url if "://" in url else "https://"+url).netloc.lower().split("@")[-1]
        if ":" in h:h=h.split(":",1)[0]
        return h[4:] if h.startswith("www.") else h
    except Exception:return None

def _tokens(name):
    stop={"inc","incorporated","corp","corporation","company","co","llc","ltd","limited","plc",
          "group","holdings","holding","the","and","of","usa","us"}
    return [x.lower() for x in re.findall(r"[A-Za-z0-9]+",name or "") if len(x)>=3 and x.lower() not in stop]

def sec_company_domain(cik,timeout=20):
    if not cik:return None
    cik=str(cik).strip().zfill(10)
    req=Request(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    website=(data.get("website") or data.get("investorWebsite") or "").strip() if isinstance(data,dict) else ""
    domain=_host(website) if website else None
    return {"official_domain":domain,"official_url":website or None,
            "domain_evidence":"sec_submissions"} if domain else None

def _unwrap_result_url(raw):
    raw=html.unescape(raw).replace("\\/","/")
    if raw.startswith("//"):raw="https:"+raw
    if raw.startswith("/url?"):
        q=parse_qs(urlparse(raw).query)
        raw=(q.get("q") or q.get("url") or [""])[0]
    if "duckduckgo.com/l/?" in raw:
        q=parse_qs(urlparse(raw).query)
        raw=unquote((q.get("uddg") or [""])[0])
    return raw if raw.startswith(("http://","https://")) else None

def _search_candidates(name,timeout=15):
    q=quote_plus(f'"{name}" official website')
    endpoints=[
        "https://www.google.com/search?num=10&q="+q,
        "https://html.duckduckgo.com/html/?q="+q,
        "https://www.bing.com/search?q="+q,
        "https://search.yahoo.com/search?p="+q,
    ]
    out=[]
    for endpoint in endpoints:
        try:
            req=Request(endpoint,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"en-US,en;q=0.9"})
            with urlopen(req,timeout=timeout) as r:body=r.read().decode("utf-8","ignore")
        except Exception:
            continue
        hrefs=re.findall(r'href=["\']([^"\']+)["\']',body,re.I)
        # Also catch plain URLs emitted by result metadata.
        hrefs += re.findall(r'https?://[^"&<>\s]+',body,re.I)
        for raw in hrefs:
            u=_unwrap_result_url(raw)
            h=_host(u) if u else None
            if not h or any(b in h for b in BLOCKED):continue
            if h not in [x[1] for x in out]:out.append((u,h))
        if len(out)>=8:break
    return out[:12]

def _first_party_match(url,name,timeout=12):
    """Require first-party content/metadata to corroborate the employer identity."""
    try:
        req=Request(url,headers=UA)
        with urlopen(req,timeout=timeout) as r:
            final=r.geturl();body=r.read(750000).decode("utf-8","ignore")
    except Exception:return None
    host=_host(final)
    if not host or any(b in host for b in BLOCKED):return None
    tokens=_tokens(name)
    if not tokens:return None
    low=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(body))).lower()
    title_m=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
    title=re.sub(r"<[^>]+>"," ",html.unescape(title_m.group(1))).lower() if title_m else ""
    # Strong structured-data evidence: Organization name or sameAs on the site.
    structured=" ".join(re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',body,re.I|re.S)).lower()
    needed=1 if len(tokens)==1 else 2
    score=max(sum(t in title for t in tokens),sum(t in structured for t in tokens),sum(t in low[:12000] for t in tokens))
    if score<min(needed,len(tokens)):return None
    return {"official_domain":host,"official_url":"https://"+host,
            "domain_evidence":"public_search_plus_first_party_identity"}

def _direct_domain_candidates(name):
    """Generate discovery candidates only; every candidate must still pass first-party verification."""
    tokens=_tokens(name)
    if not tokens:return []
    joined="".join(tokens)
    hyphen="-".join(tokens)
    slugs=list(dict.fromkeys(x for x in (joined,hyphen) if len(x)>=3))
    return [f"https://{slug}.{tld}/" for slug in slugs for tld in ("com","org","net","io","ai","co","health","care") ]

def _norm_name(value):
    return " ".join(_tokens(value))

def _wikidata_official_candidates(name,timeout=12):
    """Resolve public knowledge-graph P856 websites, then verify first-party identity."""
    try:
        api="https://www.wikidata.org/w/api.php?"+__import__("urllib.parse",fromlist=["urlencode"]).urlencode({
            "action":"wbsearchentities","search":name,"language":"en","uselang":"en",
            "type":"item","limit":5,"format":"json","origin":"*"
        })
        with urlopen(Request(api,headers=UA),timeout=timeout) as r:data=json.load(r)
    except Exception:
        return []
    wanted=_norm_name(name)
    out=[]
    for hit in data.get("search",[]):
        label=_norm_name(hit.get("label") or "")
        aliases=[_norm_name(x) for x in (hit.get("aliases") or []) if isinstance(x,str)]
        # Avoid fuzzy-name false positives. Legal suffix normalization is already
        # handled by _tokens; accept exact normalized labels/aliases only.
        if wanted not in [label,*aliases]:continue
        qid=hit.get("id")
        if not qid:continue
        try:
            with urlopen(Request(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",headers=UA),timeout=timeout) as r:
                entity=json.load(r).get("entities",{}).get(qid,{})
            for claim in (entity.get("claims",{}).get("P856") or []):
                value=(((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
                if isinstance(value,str) and value.startswith(("http://","https://")):
                    out.append(value)
        except Exception:
            continue
    return list(dict.fromkeys(out))

def _verified_domain_from_search(row,timeout=20):
    name=(row.get("company") or "").strip()
    if not name:return None
    # Prefer structured official-website evidence over guessed domains/search
    # scraping. Every knowledge-graph candidate still has to prove the employer
    # identity on the first-party destination.
    for raw in _wikidata_official_candidates(name,timeout=min(timeout,12)):
        hit=_first_party_match(raw,name,timeout=min(timeout,10))
        if hit:
            hit["domain_evidence"]="wikidata_p856_plus_first_party_identity"
            return hit
    # Public search results are discovery candidates only; acceptance still
    # requires first-party identity evidence on the destination. Search before
    # deterministic hostname candidates because it scales better across legal
    # names, DBAs, acronyms and subsidiaries.
    for raw,_ in _search_candidates(name,timeout=min(timeout,10)):
        hit=_first_party_match(raw,name,timeout=min(timeout,8))
        if hit:return hit
    # Deterministic guesses are a bounded fallback, never evidence by themselves.
    for raw in _direct_domain_candidates(name):
        hit=_first_party_match(raw,name,timeout=min(timeout,7))
        if hit:
            hit["domain_evidence"]="verified_direct_candidate_plus_first_party_identity"
            return hit
    return None

def can_resolve_company(row, allow_name_search=False):
    """Return whether this row has evidence worth spending routine network budget on.

    Routine production enrichment is evidence-first. Blind company-name web
    discovery is intentionally opt-in because it is high latency and low yield.
    """
    return bool(
        row.get("official_domain")
        or row.get("sec_cik")
        or row.get("organization_url_evidence")
        or row.get("domain_candidate_url")
        or row.get("official_url")
        # Recent certified H-1B LCA history is a strong prioritization signal for
        # this agent. It permits *discovery* by employer name, but never bypasses
        # first-party verification in _verified_domain_from_search().
        or (row.get("recent_h1b_lca") and row.get("company"))
        or (row.get("current_hiring_signal") and row.get("company"))
        or (allow_name_search and row.get("company"))
    )

def resolve_company(row, allow_name_search=False):
    if row.get("official_domain"):
        return {"official_domain":row["official_domain"],"official_url":row.get("official_url"),
                "domain_evidence":row.get("domain_evidence") or "existing_verified"}
    # Explicit employer URLs from authoritative feeders or JobPosting
    # hiringOrganization metadata are much stronger and cheaper than name search.
    # Always verify them first, including domain_candidate_url persisted by discovery.
    for field,evidence in (
        ("organization_url_evidence","jobposting_hiring_organization_plus_first_party_identity"),
        ("domain_candidate_url","persisted_candidate_plus_first_party_identity"),
        ("official_url","authoritative_url_plus_first_party_identity"),
    ):
        raw=row.get(field)
        if raw:
            hit=_first_party_match(raw,row.get("company") or "",timeout=12)
            if hit:
                hit["domain_evidence"]=evidence
                return hit
    if row.get("sec_cik"):
        hit=sec_company_domain(row["sec_cik"])
        if hit:return hit
    priority_name_search=bool((row.get("recent_h1b_lca") or row.get("current_hiring_signal")) and row.get("company"))
    return _verified_domain_from_search(row) if (allow_name_search or priority_name_search) else None
