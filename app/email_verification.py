from __future__ import annotations
import base64, html, os, re, time
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]

VERIFY_TEXT_RE=re.compile(
    r"(verify|verification|activate|activation|confirm).{0,80}(email|account)|"
    r"(check|sent|send).{0,50}(email|inbox)|email.{0,60}(verify|verification|activate|confirmation)",
    re.I|re.S,
)
LINK_RE=re.compile(r'https?://[^\s<>"\']+',re.I)
CODE_RE=re.compile(r'(?<!\d)(\d{6})(?!\d)')

def email_verification_required(text:str)->bool:
    return bool(VERIFY_TEXT_RE.search(text or ""))

def _gmail_service():
    """Use Gmail OAuth. Client secrets/token stay local and must never be committed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes=["https://www.googleapis.com/auth/gmail.readonly"]
    client=Path(os.getenv("GMAIL_OAUTH_CLIENT_FILE",ROOT/"secrets/gmail_oauth_client.json"))
    token=Path(os.getenv("GMAIL_OAUTH_TOKEN_FILE",ROOT/"generated/.gmail_token.json"))
    creds=None
    if token.exists():
        creds=Credentials.from_authorized_user_file(str(token),scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not client.exists():
            raise RuntimeError(
                "Gmail OAuth is not configured. Set GMAIL_OAUTH_CLIENT_FILE to a local OAuth client JSON file."
            )
        flow=InstalledAppFlow.from_client_secrets_file(str(client),scopes)
        creds=flow.run_local_server(port=0,open_browser=True)
        token.parent.mkdir(parents=True,exist_ok=True)
        token.write_text(creds.to_json(),encoding="utf-8")
    return build("gmail","v1",credentials=creds,cache_discovery=False)

def _parts(payload):
    yield payload
    for p in payload.get("parts") or []:
        yield from _parts(p)

def _message_text(msg):
    chunks=[]
    for p in _parts(msg.get("payload") or {}):
        data=((p.get("body") or {}).get("data") or "")
        if not data:continue
        try:
            raw=base64.urlsafe_b64decode(data+"="*((4-len(data)%4)%4)).decode("utf-8","ignore")
            chunks.append(html.unescape(raw))
        except Exception:pass
    return "\n".join(chunks)

def _safe_link(text):
    ranked=[]
    for raw in LINK_RE.findall(text or ""):
        url=html.unescape(raw).rstrip(").,;'")
        try:
            p=urlparse(url)
            if p.scheme!="https" or not p.netloc:continue
        except Exception:continue
        low=url.lower()
        score=0
        if any(x in low for x in ("verify","verification","activate","activation","confirm","candidate")):score+=10
        if any(x in low for x in ("unsubscribe","privacy","facebook","linkedin","instagram")):score-=20
        ranked.append((score,url))
    ranked.sort(key=lambda x:-x[0])
    return ranked[0][1] if ranked and ranked[0][0]>0 else None

def wait_for_verification(company="",email="",after_epoch=None,timeout=150,poll=5):
    """Poll only recent likely verification mail and return a link or six-digit code."""
    service=_gmail_service()
    after=int(after_epoch or (time.time()-300))
    terms=[f"after:{after}","newer_than:1d"]
    if company:
        clean=re.sub(r'[^A-Za-z0-9 ]+',' ',company).strip()
        if clean:terms.append(f'("{clean}" OR verification OR verify OR activation)')
    else:
        terms.append("(verification OR verify OR activation OR confirm)")
    if email:terms.append(f"to:{email}")
    query=" ".join(terms)
    deadline=time.time()+timeout
    seen=set()
    while time.time()<deadline:
        rows=service.users().messages().list(userId="me",q=query,maxResults=15).execute().get("messages",[])
        for row in rows:
            mid=row["id"]
            if mid in seen:continue
            seen.add(mid)
            msg=service.users().messages().get(userId="me",id=mid,format="full").execute()
            text=_message_text(msg)
            link=_safe_link(text)
            code=(CODE_RE.search(re.sub(r"<[^>]+>"," ",text)) or [None,None])[1]
            if link or code:
                return {"found":True,"message_id":mid,"link":link,"code":code}
        time.sleep(poll)
    return {"found":False,"reason":"No matching verification email arrived before timeout"}
