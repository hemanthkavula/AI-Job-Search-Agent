from app.sources.taleo import _exact_payload


def test_taleo_decodes_embedded_requisition_description():
    page='head 00070769101!|!GCP Data Engineer!|!00070769101!|!!*!%3Cp%3EMandatory%20Skills%3A%20SQL%20Python%20BigQuery%20Cloud%20Composer%20and%20experience%20with%20data%20warehouse%20architecture%20and%20production%20data%20pipelines%20for%20large%20enterprise%20data%20processing%20and%20ETL%20development%20requirements.%3C%2Fp%3E!|!end'
    result=_exact_payload(page,"00070769101")
    assert "BigQuery" in result
    assert "production data pipelines" in result


def test_taleo_requires_exact_id():
    assert _exact_payload("!*!%3Cp%3EExperience%20required%3C%2Fp%3E","123") == ""
