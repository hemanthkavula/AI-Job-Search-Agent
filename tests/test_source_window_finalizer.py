import json

from app import source_window_finalizer


def test_provider_specific_windows_reach_finalizer(tmp_path, monkeypatch):
    report={
        "results":[
            {"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"wd:1","source":"workday"}},
            {"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"lever:1","source":"lever"}},
        ]
    }
    inp=tmp_path/"eligible.json";out=tmp_path/"finalized.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    calls=[]

    def fake_finalize(report_path,output_path,hours=24,now=None):
        payload=json.loads(open(report_path,encoding="utf-8").read())
        source=payload["results"][0]["job"]["source"]
        calls.append((source,hours))
        result={"finalized":len(payload["results"]),"held_or_rejected":0,"results":payload["results"],"rejections":[]}
        open(output_path,"w",encoding="utf-8").write(json.dumps(result))
        return result

    monkeypatch.setattr(source_window_finalizer,"finalize_report",fake_finalize)
    result=source_window_finalizer.finalize_report_by_source(
        str(inp),str(out),hours=2.5,source_hours={"workday":6.25,"lever":2.5}
    )

    assert calls==[("workday",6.25),("lever",2.5)]
    assert result["finalized"]==2
    assert result["held_or_rejected"]==0


def test_without_source_windows_preserves_single_finalizer_call(tmp_path, monkeypatch):
    inp=tmp_path/"eligible.json";out=tmp_path/"finalized.json"
    inp.write_text(json.dumps({"results":[]}),encoding="utf-8")
    calls=[]

    def fake_finalize(report_path,output_path,hours=24,now=None):
        calls.append(hours)
        return {"finalized":0,"held_or_rejected":0,"results":[],"rejections":[]}

    monkeypatch.setattr(source_window_finalizer,"finalize_report",fake_finalize)
    result=source_window_finalizer.finalize_report_by_source(str(inp),str(out),hours=3,source_hours=None)
    assert calls==[3]
    assert result["finalized"]==0
