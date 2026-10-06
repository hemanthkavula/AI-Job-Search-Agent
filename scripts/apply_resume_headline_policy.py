from pathlib import Path

renderer = Path('app/reference_resume_formatter.py')
text = renderer.read_text(encoding='utf-8')

needle = '''def _summary_parts(text):\n'''
helper = '''def resume_branding_headline(title):\n    \"\"\"Return a truthful JD-aligned headline without inflating held seniority.\n\n    The fixed employment history remains Senior Data Engineer / Data Engineer.\n    The top headline may add one target specialty, but never adopts Staff,\n    Principal, Lead, Director, or other unheld seniority from the vacancy.\n    \"\"\"\n    raw = re.sub(r\"\\s+\", \" \", str(title or \"\")).strip().casefold()\n    base = \"Senior Data Engineer\"\n\n    specialty_rules = (\n        (r\"\\banalytics?\\s+engineer(?:ing)?\\b\", \"Analytics Engineering\"),\n        (r\"\\bdata\\s+platform\\s+engineer(?:ing)?\\b|\\bplatform\\s+data\\s+engineer(?:ing)?\\b\", \"Data Platform Engineering\"),\n        (r\"\\blakehouse\\b\", \"Lakehouse Engineering\"),\n        (r\"\\bstream(?:ing)?\\s+data\\b|\\breal[- ]time\\s+data\\b\", \"Streaming Data Engineering\"),\n        (r\"\\bdata\\s+warehouse|\\bwarehouse\\s+engineer(?:ing)?\\b\", \"Data Warehousing\"),\n        (r\"\\betl\\b|\\belt\\b\", \"ETL/ELT Engineering\"),\n    )\n    for pattern, specialty in specialty_rules:\n        if re.search(pattern, raw, flags=re.I):\n            return f\"{base} | {specialty}\"\n    return base\n\n\n'''
if 'def resume_branding_headline(title):' not in text:
    if needle not in text:
        raise RuntimeError('Could not locate summary helper insertion point')
    text = text.replace(needle, helper + needle, 1)

old = '_run(header, canonical_resume_title(job.title), normal)'
new = '_run(header, resume_branding_headline(job.title), normal)'
if old not in text and new not in text:
    raise RuntimeError('Could not locate headline render call')
text = text.replace(old, new, 1)
renderer.write_text(text, encoding='utf-8')

test = Path('tests/test_resume_headline_policy.py')
test.write_text('''from app.reference_resume_formatter import resume_branding_headline\n\n\ndef test_headline_does_not_inflate_seniority():\n    assert resume_branding_headline(\"Staff Analytics Engineer\") == \"Senior Data Engineer | Analytics Engineering\"\n    assert resume_branding_headline(\"Principal Analytics Engineer\") == \"Senior Data Engineer | Analytics Engineering\"\n    assert resume_branding_headline(\"Lead Data Platform Engineer\") == \"Senior Data Engineer | Data Platform Engineering\"\n\n\ndef test_headline_keeps_data_engineer_base_for_same_family_roles():\n    assert resume_branding_headline(\"Senior Data Engineer\") == \"Senior Data Engineer\"\n    assert resume_branding_headline(\"Staff Data Engineer\") == \"Senior Data Engineer\"\n    assert resume_branding_headline(\"Data Engineer\") == \"Senior Data Engineer\"\n\n\ndef test_headline_adds_only_one_truthful_specialty():\n    assert resume_branding_headline(\"Analytics Engineer\") == \"Senior Data Engineer | Analytics Engineering\"\n    assert resume_branding_headline(\"Data Platform Engineer\") == \"Senior Data Engineer | Data Platform Engineering\"\n    assert resume_branding_headline(\"Streaming Data Engineer\") == \"Senior Data Engineer | Streaming Data Engineering\"\n''', encoding='utf-8')

print('Resume headline policy applied')
