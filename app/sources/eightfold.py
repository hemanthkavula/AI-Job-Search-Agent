from __future__ import annotations
import html, json, re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.8","Accept":"text/html,application/xhtml+xml"}
JSON_UA={"User-Agent":"AI-Job-Search-Agent/0.8","Accept":"application/json,text/plain,*/*"}

def _get(url: str, timeout: int = 25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _get_json(url: str, timeout: int = 25, referer: str = ""):
    headers=dict(JSON_UA)
    if referer:
        headers["Referer"]=referer
    with urlopen(Request(url,headers=headers),timeout=timeout) as resp:
        raw=resp.read().decode("utf-8","replace")
    try:
        return json.loads(raw)
    except Exception:
        return None


def _domain_from_page(body: str, careers_url: str) -> str:
    decoded=html.unescape(body or "")
    for pattern in (
        r'(?i)["\']domain["\']\s*:\s*["\']([^"\']+)["\']',
        r'(?i)window\._EF_GROUP_ID\s*=\s*["\']([^"\']+)["\']',
        r'(?i)["\']groupId["\']\s*:\s*["\']([^"\']+)["\']',
    ):
        m=re.search(pattern,decoded)
        if m and "." in m.group(1):
            return m.group(1).strip()
    host=(urlparse(careers_url).hostname or "")
    slug=host.split(".",1)[0] if host else ""
    return f"{slug}.com" if slug else host


def _walk(node):
    stack=[node]
    while stack:
        value=stack.pop()
        if isinstance(value,dict):
            yield value
            stack.extend(value.values())
        elif isinstance(value,list):
            stack.extend(value)


def _plain(value) -> str:
    text=html.unescape(str(value or ""))
    text=re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ",text)
    text=re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>","\n",text)
    text=re.sub(r"(?s)<[^>]+>"," ",text)
    return re.sub(r"[ \t\r\f\v]+"," ",text).strip()


def _normalize_position(company: str, host: str, identifier: str, node: dict) -> dict | None:
    if not isinstance(node,dict):
        return None
    title=str(node.get("posting_name") or node.get("name") or node.get("title") or node.get("jobTitle") or "").strip()
    desc=_plain(node.get("job_description") or node.get("jobDescription") or node.get("descriptionHtml") or node.get("description") or "")
    if not title:
        return None
    pos_id=str(node.get("id") or node.get("position_id") or node.get("positionId") or identifier or "").strip()
    ats_id=str(node.get("ats_job_id") or node.get("atsJobId") or node.get("display_job_id") or node.get("displayJobId") or pos_id).strip()
    canonical=str(node.get("canonicalPositionUrl") or node.get("canonical_position_url") or node.get("positionUrl") or node.get("position_url") or "").strip()
    if canonical.startswith("/"):
        canonical=host+canonical
    if not canonical:
        canonical=f"{host}/careers/job/{pos_id or identifier}"
    loc=node.get("location")
    if not loc and isinstance(node.get("locations"),list):
        loc=" | ".join(str(x) for x in node.get("locations") if x)
    return {
        "external_id":f"eightfold:{company}:{ats_id or pos_id or identifier}",
        "source":"eightfold",
        "company_key":company,
        "company":company,
        "title":title,
        "location":str(loc).strip() if loc else None,
        "url":canonical,
        "original_url":canonical,
        "ats_provider":"eightfold",
        "ats_identifier":urlparse(host).hostname.split(".",1)[0] if urlparse(host).hostname else None,
        "job_id":pos_id or None,
        "requisition_id":ats_id or None,
        "employment_type":node.get("employmentType") or node.get("employment_type"),
        "posted_at":node.get("postedTs") or node.get("creationTs") or node.get("t_create") or node.get("t_update"),
        "description":desc,
        "description_complete":bool(desc.strip()),
        "exact_job_metadata_source":"eightfold_public_api",
    }


def fetch_job(company: str, job_url: str, timeout: int = 25) -> dict | None:
    """Fetch one exact Eightfold posting by its public position id."""
    parsed=urlparse(job_url or "")
    host=f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else ""
    parts=[x for x in parsed.path.split("/") if x]
    try:
        marker=next(i for i,x in enumerate(parts) if x.lower()=="job")
        position_id=parts[marker+1]
    except Exception:
        position_id=parts[-1] if parts else ""
    position_id=str(position_id).split("-",1)[0] if str(position_id).isdigit() else str(position_id)
    if not host or not position_id:
        return None
    page=_get(job_url,timeout)
    domain=_domain_from_page(page,job_url)

    detail_urls=[
        f"{host}/api/pcsx/position_details?"+urlencode({"position_id":position_id,"domain":domain,"hl":"en"}),
        f"{host}/api/apply/v2/jobs/{position_id}/jobs?"+urlencode({"domain":domain}),
        f"{host}/api/apply/v2/jobs/{position_id}?"+urlencode({"domain":domain}),
    ]
    for url in detail_urls:
        try:
            payload=_get_json(url,timeout,referer=job_url)
        except Exception:
            payload=None
        if payload is None:
            continue
        best=None
        for node in _walk(payload):
            row=_normalize_position(company,host,position_id,node)
            if not row:
                continue
            if not best or len(row.get("description") or "")>len(best.get("description") or ""):
                best=row
        if best and (best.get("description") or "").strip():
            return best

    # Fallback: the public search endpoints expose canonical title/location even
    # when the detail route is gated. Scan enough pages to find the supplied id,
    # then use that record if it already carries a description.
    for path in ("/api/pcsx/search","/api/apply/v2/jobs"):
        for start in range(0,500,10):
            params={"domain":domain,"query":"","location":"","start":start,"num":10,"sort_by":"timestamp"}
            try:
                payload=_get_json(f"{host}{path}?"+urlencode(params),timeout,referer=job_url)
            except Exception:
                payload=None
            if not isinstance(payload,dict):
                break
            container=payload.get("data") if isinstance(payload.get("data"),dict) else payload
            positions=container.get("positions") if isinstance(container,dict) else None
            if not isinstance(positions,list) or not positions:
                break
            for node in positions:
                nid=str(node.get("id") or node.get("position_id") or node.get("positionId") or "")
                if nid!=position_id:
                    continue
                row=_normalize_position(company,host,position_id,node)
                if row:
                    return row
            if len(positions)<10:
                break
    return None


def _positions(body: str) -> list[dict]:
    # Eightfold tenants serialize the position collection in several forms
    # (plain JSON, escaped hydration JSON, and whitespace-separated script data).
    # Try each marker rather than assuming one exact HTML representation.
    candidates=[body, body.replace('\\\"','"')]
    for candidate in candidates:
        rows=_positions_from(candidate)
        if rows:return rows
    return []

def _positions_from(body: str) -> list[dict]:
    m=re.search(r'["\\\']positions["\\\']\\s*:\\s*',body,re.I)
    start=m.start() if m else -1
    if start < 0:
        return []
    start=body.find("[",m.end() if m else start)
    if start < 0:
        return []
    depth=0; in_string=False; escape=False
    for i in range(start,len(body)):
        ch=body[i]
        if in_string:
            if escape: escape=False
            elif ch=="\\": escape=True
            elif ch=='"': in_string=False
            continue
        if ch=='"': in_string=True
        elif ch=="[": depth+=1
        elif ch=="]":
            depth-=1
            if depth==0:
                try:return json.loads(body[start:i+1])
                except Exception:return []
    return []

def _next_data_positions(body: str) -> list[dict]:
    for raw in re.findall(r'<script[^>]+id=["\\\']__NEXT_DATA__["\\\'][^>]*>(.*?)</script>',body,re.I|re.S):
        try:data=json.loads(raw)
        except Exception:continue
        stack=[data]
        while stack:
            node=stack.pop()
            if isinstance(node,dict):
                value=node.get("positions")
                if isinstance(value,list) and value:return value
                stack.extend(node.values())
            elif isinstance(node,list):stack.extend(node)
    return []

def fetch_jobs(company: str, careers_url: str, timeout: int = 25) -> list[dict]:
    """Fetch public Eightfold career positions embedded in the career page."""
    body=_get(careers_url,timeout)
    out=[]
    positions=_positions(body) or _next_data_positions(body)
    for j in positions:
        title=str(j.get("posting_name") or j.get("name") or "")
        desc=str(j.get("job_description") or "")
        hay=(title+" "+desc[:2500]).lower()
        if not any(term in hay for term in ("data engineer","data engineering","data platform engineer","big data engineer","etl engineer")):
            continue
        loc=j.get("location") or ", ".join(j.get("locations") or [])
        ident=j.get("ats_job_id") or j.get("display_job_id") or j.get("id")
        url=j.get("canonicalPositionUrl") or careers_url.rstrip("/")+"/job/"+str(j.get("id") or "")
        out.append({
            "external_id":f"eightfold:{company}:{ident}","source":"eightfold","company_key":company,
            "title":title,"location":loc or None,"url":url,"original_url":url,
            "ats_provider":"eightfold","ats_identifier":careers_url,"job_id":ident,
            "description":desc,"description_complete":bool(desc.strip()),
            "updated_at":j.get("t_update") or j.get("t_create"),
        })
    print(f"Eightfold / {company}: {len(out)} DE jobs",flush=True)
    return out
