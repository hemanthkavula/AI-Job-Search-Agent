from __future__ import annotations

import html, json, re, time
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/json,*/*"}

def _safe_url(url: str) -> str:
    parts=urlsplit(str(url).strip())
    host=parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:host=f"{host}:{parts.port}"
    path=quote(parts.path,safe="/%:@!$&'()*+,;=-._~")
    query=quote(parts.query,safe="=&?/:;+,%@!$'()*-._~")
    fragment=quote(parts.fragment,safe="=&?/:;+,%@!$'()*-._~")
    return urlunsplit((parts.scheme,host,path,query,fragment))

def _get(url: str, timeout: int=25, retries: int=3) -> str:
    """Fetch a UKG page with bounded retries for truncated/transient responses."""
    last=None
    safe=_safe_url(url)
    for attempt in range(max(1,retries)):
        try:
            with urlopen(Request(safe,headers=UA),timeout=timeout) as resp:
                return resp.read().decode("utf-8","replace")
        except HTTPError as exc:
            last=exc
            if exc.code not in (408,425,429,500,502,503,504):
                raise
        except (IncompleteRead,URLError,TimeoutError,OSError,UnicodeError,ValueError) as exc:
            last=exc
        if attempt+1<max(1,retries):
            time.sleep(0.75*(2**attempt))
    raise last or RuntimeError(f"UKG request failed: {safe}")

def _plain(value) -> str:
    value=html.unescape(str(value or ""))
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _jobposting(body: str) -> list[dict]:
    out=[]
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            node=stack.pop()
            if not isinstance(node,dict):continue
            if node.get("@type")=="JobPosting":out.append(node)
            graph=node.get("@graph")
            if isinstance(graph,list):stack.extend(graph)
    return out

def _location(j: dict) -> str|None:
    loc=j.get("jobLocation")
    rows=loc if isinstance(loc,list) else [loc] if loc else []
    vals=[]
    for row in rows:
        if not isinstance(row,dict):continue
        addr=row.get("address") or {}
        if isinstance(addr,dict):
            text=", ".join(str(addr.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
            if text:vals.append(text)
    return "; ".join(vals) or None

def _embedded_opportunities(body: str) -> list[dict]:
    """Decode UKG opportunity objects embedded in the public board bootstrap."""
    out=[]; seen=set(); decoder=json.JSONDecoder()
    # Opportunity records have a stable Id + Featured prefix; raw_decode safely
    # handles nested Locations/Address objects without brittle regex matching.
    for m in re.finditer(r'\{"Id":"[0-9a-fA-F-]{36}","Featured":', body):
        try:
            row,_=decoder.raw_decode(body[m.start():])
        except Exception:
            continue
        if not isinstance(row,dict) or not row.get("Title") or not row.get("Id"):
            continue
        ident=str(row["Id"])
        if ident in seen: continue
        seen.add(ident); out.append(row)
    return out

def _embedded_location(row: dict) -> str|None:
    vals=[]
    for loc in row.get("Locations") or []:
        if not isinstance(loc,dict): continue
        addr=loc.get("Address") or {}
        state=addr.get("State") or {} if isinstance(addr,dict) else {}
        country=addr.get("Country") or {} if isinstance(addr,dict) else {}
        parts=[]
        if isinstance(addr,dict) and addr.get("City"): parts.append(str(addr["City"]))
        if isinstance(state,dict) and state.get("Code"): parts.append(str(state["Code"]))
        if isinstance(country,dict) and country.get("Code"): parts.append(str(country["Code"]))
        label=", ".join(parts) or _plain(loc.get("LocalizedName") or loc.get("LocalizedDescription"))
        if label and label not in vals: vals.append(label)
    return "; ".join(vals) or None

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect public UKG/UltiPro postings exposed by the tenant's rendered board.

    UKG tenants vary substantially. This adapter intentionally uses public
    structured JobPosting data and board links, with the generic crawler still
    available as fallback for unsupported tenant variants.
    """
    body=_get(search_url,timeout)
    out=[];seen=set()
    terms=("data engineer","data engineering","data platform engineer","data infrastructure engineer","database engineer","data pipeline engineer","etl engineer","analytics engineer")
    for row in _embedded_opportunities(body):
        title=_plain(row.get("Title")); desc=_plain(row.get("BriefDescription"))
        if not any(x in (title+" "+desc[:2500]).lower() for x in terms): continue
        ident=str(row.get("Id")); url=search_url.rstrip("/")+"/OpportunityDetail?opportunityId="+ident
        if ident in seen: continue
        seen.add(ident)
        out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
          "title":title,"location":_embedded_location(row),"url":url,"original_url":url,
          "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
          "description":desc,"description_complete":False,
          "updated_at":row.get("PostedDate")})
    if out:return out

    jobs=_jobposting(body)
    for j in jobs:
        title=_plain(j.get("title"))
        desc=_plain(j.get("description"))
        hay=(title+" "+desc[:2500]).lower()
        if not any(x in hay for x in ("data engineer","data engineering","data platform engineer","data infrastructure engineer","etl engineer","analytics engineer")):continue
        url=str(j.get("url") or search_url)
        ident=j.get("identifier") or url
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or url
        ident=str(ident)
        if ident in seen:continue
        seen.add(ident)
        out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
          "title":title,"location":_location(j),"url":url,"original_url":url,
          "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
          "description":desc,"description_complete":bool(desc),
          "updated_at":j.get("datePosted") or j.get("validThrough")})
    if out:return out

    # Some legacy UltiPro boards render ordinary opportunity links server-side.
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',body,re.I)
    links=[];seen_links=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href))
        low=url.lower()
        if ("opportunitydetail" in low or "/job/" in low or "/jobs/" in low) and url not in seen_links:
            seen_links.add(url);links.append(url)
    for url in links[:200]:
        try:detail=_get(url,timeout)
        except Exception:continue
        rows=_jobposting(detail)
        for j in rows:
            title=_plain(j.get("title"));desc=_plain(j.get("description"))
            hay=(title+" "+desc[:2500]).lower()
            if not any(x in hay for x in ("data engineer","data engineering","data platform engineer","data infrastructure engineer","etl engineer","analytics engineer")):continue
            ident=j.get("identifier") or url
            if isinstance(ident,dict):ident=ident.get("value") or url
            ident=str(ident)
            if ident in seen:continue
            seen.add(ident)
            out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
              "title":title,"location":_location(j),"url":url,"original_url":url,
              "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
              "description":desc,"description_complete":bool(desc),
              "updated_at":j.get("datePosted") or j.get("validThrough")})
    return out


def fetch_job(company: str, url: str, timeout: int=25) -> dict | None:
    """Resolve one exact UKG/UltiPro opportunity from the embedded full-detail object."""
    from urllib.parse import parse_qs
    parsed=urlparse(str(url or ""))
    query=parse_qs(parsed.query)
    opportunity_id=(query.get("opportunityId") or query.get("opportunityid") or [""])[0]
    if not opportunity_id:
        return None
    try:
        body=_get(url,timeout)
    except Exception:
        return None
    row=next((item for item in _embedded_opportunities(body) if str(item.get("Id") or "").lower()==str(opportunity_id).lower()),None)
    if not row:
        marker="new US.Opportunity.CandidateOpportunityDetail("
        start=body.find(marker)
        if start>=0:
            fragment=body[start+len(marker):].lstrip()
            try:
                decoded,_=json.JSONDecoder().raw_decode(fragment)
                if isinstance(decoded,dict) and str(decoded.get("Id") or "").lower()==str(opportunity_id).lower():
                    row=decoded
            except Exception:
                row=None
    if not row:
        return None
    title=_plain(row.get("Title"))
    desc=_plain(row.get("Description") or row.get("BriefDescription"))
    board_name=_plain(row.get("ApplicationJobBoardName"))
    brand_match=re.search(r'(?is)<a[^>]+class=["\'][^"\']*navbar-brand[^"\']*["\'][^>]*>.*?<img[^>]+alt=["\']([^"\']+)["\']',body)
    brand_company=_plain(brand_match.group(1)) if brand_match else ""
    supplied=_plain(company)
    if supplied.lower() in {"","company","unknown","unknown company","job from supplied link"}:
        supplied=""
    resolved_company=board_name or brand_company or supplied
    req=str(row.get("RequisitionNumber") or opportunity_id)
    return {
        "external_id":f"ukg:{resolved_company or 'company'}:{opportunity_id}",
        "source":"ukg",
        "company_key":resolved_company,
        "company":resolved_company,
        "title":title,
        "location":_embedded_location(row),
        "employment_type":"Full Time" if row.get("FullTime") is True else None,
        "url":url,
        "original_url":url,
        "ats_provider":"ukg",
        "ats_identifier":parsed.netloc,
        "job_id":opportunity_id,
        "requisition_id":req,
        "description":desc,
        "description_complete":bool(desc),
        "posted_at":row.get("PostedDate"),
        "exact_job_metadata_source":"ukg_embedded_opportunity_detail",
    }
