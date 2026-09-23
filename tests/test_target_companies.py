from app.target_companies import load_targets,match_target,annotate_jobs

def test_complete_user_target_universe_is_loaded():
    payload=load_targets()
    assert payload["counts"]=={"unique_companies":234,"h1b_targets":188,"vendor_consulting_staffing":60}
    names={x["company"] for x in payload["companies"]}
    for name in ("Amazon","Capital One","Databricks","Tata Consultancy Services (TCS)","TEKsystems","Mitchell Martin","Wells Fargo","Coinbase","Citadel Securities","Experian"):
        assert name in names
    assert "Fidelity Investments" not in names
    assert "Cigna Healthcare" not in names
    assert "Target" not in names

def test_target_aliases_match_common_employer_names():
    assert match_target("JPMorgan Chase & Co.")["company"]=="JPMorgan Chase"
    assert match_target("TCS")["company"]=="Tata Consultancy Services (TCS)"
    assert match_target("Broadcom")["company"]=="VMware/Broadcom"

def test_discovered_jobs_are_annotated_without_filtering_non_targets():
    jobs=[{"company_key":"Capital One"},{"company_key":"Another Employer"}]
    out=annotate_jobs(jobs)
    assert out[0]["target_company"] is True
    assert out[1]["target_company"] is False
    assert len(out)==2
