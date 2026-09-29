import pytest
from app.llm_resume_writer import validate_generated_resume


def profile():
    return {"experience":[
        {"company":"Fidelity Investments","title":"Senior Data Engineer","dates":"Jan 2025 – Present","location":"Jersey City, NJ"},
        {"company":"Cigna Healthcare","title":"Data Engineer","dates":"Jan 2022 – Dec 2023","location":"Bangalore"},
        {"company":"Target Corporation","title":"Data Engineer","dates":"Jan 2020 – Dec 2021","location":"Bangalore"},
    ]}


def valid():
    return {"summary":"Tailored summary","skills":{"Languages":["Python"]},"experience":[
        {"company":"Fidelity Investments","bullets":["x"]*8},
        {"company":"Cigna Healthcare","bullets":["x"]*7},
        {"company":"Target Corporation","bullets":["x"]*6},
    ]}


def test_generated_resume_contract_accepts_canonical_history():
    assert validate_generated_resume(valid(),profile())


@pytest.mark.parametrize("mutate",[
    lambda r:r["experience"].reverse(),
    lambda r:r["experience"].append({"company":"Invented Employer","bullets":["x"]}),
    lambda r:r["experience"][0].update(title="Invented Title"),
    lambda r:r["experience"][0].update(dates="Invented Dates"),
    lambda r:r["experience"][1].update(location="Invented Location"),
    lambda r:r["experience"][2].update(bullets=["x"]*5),
])
def test_generated_resume_contract_rejects_history_mutations(mutate):
    result=valid();mutate(result)
    with pytest.raises(RuntimeError):validate_generated_resume(result,profile())
