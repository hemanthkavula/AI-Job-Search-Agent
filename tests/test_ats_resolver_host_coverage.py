from app import ats_resolver

def test_candidate_links_recognize_more_ats_hosts():
    page = '<a href="https://apply.workable.com/example/j/ABC123/">Workable</a><a href="https://example.teamtailor.com/jobs/789-data-engineer">Teamtailor</a>'
    links = ats_resolver._candidate_links(page, "https://board.example/job/1")
    assert len(links) == 2
    assert any("workable.com" in x for x in links)
    assert any("teamtailor.com" in x for x in links)
