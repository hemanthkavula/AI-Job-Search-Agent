import json
from app.sources import talentreef

class _Resp:
    def __init__(self,payload):
        self.payload=payload
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.payload).encode("utf-8")

def test_talentreef_client_scoped_mapping(monkeypatch):
    seen={}
    payload={"hits":{"hits":[{"_id":"42","_source":{
        "clientId":"123","jobTitle":"Senior Data Engineer",
        "jobDescription":"Build Python and SQL pipelines",
        "location":{"city":"Dallas","state":"TX","country":"US"},
        "applyUrl":"https://apply.jobappnetwork.com/job/42",
        "employmentType":"Full Time"
    }}]}}
    def fake_urlopen(req,timeout=20):
        seen["body"]=json.loads(req.data.decode("utf-8"))
        return _Resp(payload)
    monkeypatch.setattr(talentreef,"urlopen",fake_urlopen)
    jobs=talentreef.fetch_jobs("Example Employer","123",page_size=100,max_pages=1)
    assert seen["body"]["query"]["bool"]["filter"][0]["term"]["clientId"]=="123"
    assert jobs[0]["title"]=="Senior Data Engineer"
    assert jobs[0]["location"]=="Dallas, TX, US"
    assert jobs[0]["source"]=="talentreef"
    assert jobs[0]["description_complete"] is True

def test_talentreef_requires_client_id_or_search_url():
    try:
        talentreef.fetch_jobs("Example Employer","")
        assert False, "expected ValueError"
    except ValueError:
        pass

def test_talentreef_public_board_fallback(monkeypatch):
    from app.sources import career_site
    monkeypatch.setattr(career_site,"fetch_jobs",lambda company,url,pattern:[{
        "title":"Data Engineer","url":url+"/jobs/42","description":"Build pipelines"
    }])
    jobs=talentreef.fetch_jobs("Example Employer","",search_url="https://apply.jobappnetwork.com/example/en")
    assert jobs[0]["source"]=="talentreef"
    assert jobs[0]["source_family"]=="direct_ats_public_board"
    assert jobs[0]["ats_provider"]=="talentreef"
