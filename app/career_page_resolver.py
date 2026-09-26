from __future__ import annotations
import re
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
from app.source_registry import detect_ats

UA={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"}
CAREER_WORDS=("careers","career","jobs","join us","join-us","work with us","opportunities")

def _get(url,timeout=15):
    with urlopen(Request(url,headers=UA),timeout=timeout) as r:
        return r.geturl(),r.read().decode("utf-8","ignore")

def resolve(official_domain,timeout=15):
    """Resolve an employer domain to its public career page and ATS when discoverable."""
    if not official_domain:return None
    root=official_domain if "://" in official_domain else "https://"+official_domain
    root=root.rstrip("/")+"/"
    candidates=[]
    try:
        final,body=_get(root,timeout)
        for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',body,re.I|re.S):
            text=re.sub("<[^>]+>"," ",label).lower()
            if any(w in text or w in href.lower() for w in CAREER_WORDS):
                candidates.append(urljoin(final,href))
    except Exception:pass
    candidates += [urljoin(root,p) for p in ("careers","jobs","careers/jobs")]
    seen=set()
    for url in candidates:
        if url in seen:continue
        seen.add(url)
        try:
            final,body=_get(url,timeout)
            provider,ident=detect_ats(final)
            if not provider:
                # Outbound job links reveal hosted ATS boards; script assets reveal
                # branded/embedded ATS layers (notably Phenom) even when the browser
                # remains on the employer's own careers domain.
                for attr, link in re.findall(r'(href|src)=["\']([^"\']+)["\']',body,re.I):
                    absolute=urljoin(final,link)
                    embedded_provider,embedded_ident=detect_ats(absolute)
                    if embedded_provider:
                        if attr.lower()=="src":
                            return {"careers_url":final,"ats_provider":embedded_provider,"ats_identifier":embedded_ident}
                        return {"careers_url":absolute,"ats_provider":embedded_provider,"ats_identifier":embedded_ident}
            if provider:return {"careers_url":final,"ats_provider":provider,"ats_identifier":ident}
            if any(x in body.lower() for x in ("jobposting","job opening","open positions","search jobs")):
                return {"careers_url":final,"ats_provider":"career_site","ats_identifier":urlparse(final).netloc}
        except Exception:continue
    return None
