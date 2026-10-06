import json

from app.sources import ashby


class _Response:
    def __enter__(self):
        return self

    def __exit__(self,*args):
        return False

    def read(self):
        return json.dumps({"jobs":[]}).encode("utf-8")


def test_ashby_board_name_with_spaces_is_url_encoded(monkeypatch):
    captured={}

    def fake_urlopen(request,timeout):
        captured["url"]=request.full_url
        captured["timeout"]=timeout
        return _Response()

    monkeypatch.setattr(ashby,"urlopen",fake_urlopen)

    assert ashby.fetch_jobs("superhuman platform inc",timeout=7)==[]
    assert "/superhuman%20platform%20inc?" in captured["url"]
    assert "includeCompensation=true" in captured["url"]
    assert captured["timeout"]==7
