from pathlib import Path
import scripts.cleanup_resumes as cr

def test_inventory_only_removes_duplicate_with_protected_peer(tmp_path,monkeypatch):
    resumes=tmp_path/"generated"/"resumes";resumes.mkdir(parents=True)
    protected=resumes/"company-a"/"resume.pdf";protected.parent.mkdir()
    duplicate=resumes/"old"/"copy.pdf";duplicate.parent.mkdir()
    unique=resumes/"other"/"unique.pdf";unique.parent.mkdir()
    protected.write_bytes(b"same");duplicate.write_bytes(b"same");unique.write_bytes(b"unique")
    monkeypatch.setattr(cr,"ROOT",tmp_path)
    monkeypatch.setattr(cr,"RESUMES",resumes)
    monkeypatch.setattr(cr,"_ledger_reference_sets",lambda:({protected.resolve()},{protected.parent.resolve()}))
    monkeypatch.setattr(cr,"confirmed_resume_names",lambda:set())
    rows,removable,_,_=cr.inventory()
    assert removable==[duplicate]
    statuses={Path(x["path"]).name:x["status"] for x in rows}
    assert statuses["resume.pdf"]=="KEEP_REFERENCED"
    assert statuses["copy.pdf"]=="DUPLICATE"
    assert statuses["unique.pdf"]=="ORPHAN_CANDIDATE"

def test_confirmed_filename_is_protected(tmp_path,monkeypatch):
    resumes=tmp_path/"generated"/"resumes";resumes.mkdir(parents=True)
    p=resumes/"old"/"submitted.pdf";p.parent.mkdir();p.write_bytes(b"x")
    monkeypatch.setattr(cr,"ROOT",tmp_path)
    monkeypatch.setattr(cr,"RESUMES",resumes)
    monkeypatch.setattr(cr,"_ledger_reference_sets",lambda:(set(),set()))
    monkeypatch.setattr(cr,"confirmed_resume_names",lambda:{"submitted.pdf"})
    rows,removable,_,_=cr.inventory()
    assert not removable
    assert rows[0]["status"]=="KEEP_CONFIRMED_HISTORY"
