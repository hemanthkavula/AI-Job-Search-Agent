from datetime import datetime, timezone

from app.jd_finalizer import _official_posted_at


def test_official_posted_at_prefers_jsonld_dateposted():
    page='''<html><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "title":"Data Engineer","datePosted":"2026-09-23T10:00:00-04:00"
    }</script></html>'''
    ts,label=_official_posted_at(page,datetime(2026,9,27,18,0,tzinfo=timezone.utc))
    assert ts.isoformat()=="2026-09-23T14:00:00+00:00"
    assert label=="2026-09-23T10:00:00-04:00"


def test_official_posted_at_parses_employer_relative_age():
    page="<html><body><div>Posted 4 days ago</div></body></html>"
    now=datetime(2026,9,27,22,0,tzinfo=timezone.utc)
    ts,label=_official_posted_at(page,now)
    assert ts==datetime(2026,9,23,22,0,tzinfo=timezone.utc)
    assert label.lower()=="posted 4 days ago"
