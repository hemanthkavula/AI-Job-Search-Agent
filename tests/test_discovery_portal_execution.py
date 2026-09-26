import app.discovery as discovery

def test_enabled_portal_is_executed(monkeypatch,tmp_path):
    calls=[]
    job={"external_id":"wellfound:1","source":"wellfound","company_key":"Example","title":"Data Engineer","url":"https://example.invalid/job/1","description":"data pipelines sql spark","discovery_only":True}
    monkeypatch.setattr(discovery,"discovery_portal_jobs",lambda provider,url,pattern,timeout=20,hours=None: calls.append((provider,hours)) or [job])
    monkeypatch.setattr(discovery,"resolve_original_ats",lambda row: row)
    monkeypatch.setattr(discovery,"learn_from_jobs",lambda jobs,registry: [])
    monkeypatch.setattr(discovery,"load_registry",lambda path:{})
    rows,errors=discovery.discover({"discovery_portal":[{"provider":"wellfound","company":"Wellfound","enabled":True,"search_url":"https://example.invalid/jobs","job_url_pattern":".+"}]},only_source="wellfound",registry_path=tmp_path/"sources.json",health_path=tmp_path/"health.json")
    assert not errors
    assert calls and calls[0][0]=="wellfound"\n    assert calls[0][1] is not None
    assert len(rows)==1
