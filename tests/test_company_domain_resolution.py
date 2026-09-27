import json

from app import company_domain_resolver, company_universe


class _Response:
    def __init__(self,payload,url="https://www.wikidata.org/"):
        self.payload=payload
        self._url=url
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):return self.payload
    def geturl(self):return self._url


def test_wikidata_official_website_requires_exact_normalized_identity(monkeypatch):
    search={"search":[{"id":"Q1","label":"Example Corporation","aliases":["Example Corp"]}]}
    entity={"entities":{"Q1":{"claims":{"P856":[{"mainsnak":{"datavalue":{"value":"https://example.test/"}}}]}}}}
    def fake_open(req,timeout=12):
        url=getattr(req,"full_url",str(req))
        payload=entity if "Special:EntityData" in url else search
        return _Response(json.dumps(payload).encode(),url)
    monkeypatch.setattr(company_domain_resolver,"urlopen",fake_open)
    assert company_domain_resolver._wikidata_official_candidates("Example Corp")==["https://example.test/"]


def test_domain_budget_skips_employers_that_already_have_executable_source(monkeypatch,tmp_path):
    sources=tmp_path/"sources.json"
    sources.write_text(json.dumps({"career_site":[]}),encoding="utf-8")
    monkeypatch.setattr(company_universe,"ROOT",tmp_path)
    monkeypatch.setattr(company_universe,"collect_company_feeders",lambda enabled=None:([],[]))
    registry={
        "already covered":{"company":"Already Covered","careers_url":"https://jobs.example.test","ats_provider":"career_site"},
        "needs source":{"company":"Needs Source"},
    }
    monkeypatch.setattr(company_universe,"load_registry",lambda *a,**k:registry)
    monkeypatch.setattr(company_universe,"save_registry",lambda *a,**k:None)
    monkeypatch.setattr(company_universe,"load_source_registry",lambda:{})
    monkeypatch.setattr(company_universe,"save_source_registry",lambda reg:None)
    attempted=[]
    def fake_resolve(row,allow_name_search=False):
        attempted.append(row["company"])
        assert allow_name_search is True
        return None
    monkeypatch.setattr(company_universe,"resolve_company",fake_resolve)
    company_universe.build("sources.json",registry_path=tmp_path/"registry.json",domain_budget=10,career_budget=0,retry_days=0,deep_domain_search=True)
    assert attempted==["Needs Source"]
