from pathlib import Path

source_path = Path("scripts/continue_latest_commit.py")
source = source_path.read_text(encoding="utf-8")

# The patch script embeds source-code snippets in triple-quoted Python strings.
# Preserve the literal backslash-t used by the resume formatter instead of
# allowing Python to turn it into an actual tab before matching the file.
source = source.replace(
    r'    _run(p.add_run("\t"+base["dates"]),9,False,GRAY)',
    r'    _run(p.add_run("\\t"+base["dates"]),9,False,GRAY)',
)
source = source.replace(
    r'    _run(company_p.add_run("\t"+base["dates"]),9.25,False,GRAY)',
    r'    _run(company_p.add_run("\\t"+base["dates"]),9.25,False,GRAY)',
)

exec(compile(source, str(source_path), "exec"), {"__name__": "__main__"})

# python-docx rebuilds Paragraph wrapper objects each time doc.paragraphs is read,
# so object-identity list.index() is not stable. Locate the employer paragraph by
# its text position instead and then inspect the following title/first-bullet nodes.
test_path = Path("tests/test_reference_resume_formatter_layout.py")
test_text = test_path.read_text(encoding="utf-8")
old = '''    company=next(p for p in doc.paragraphs if p.text.startswith("Fidelity Investments"))
    idx=doc.paragraphs.index(company); title=doc.paragraphs[idx+1]; first=doc.paragraphs[idx+2]
'''
new = '''    paragraphs=doc.paragraphs
    idx=next(i for i,p in enumerate(paragraphs) if p.text.startswith("Fidelity Investments"))
    company=paragraphs[idx]; title=paragraphs[idx+1]; first=paragraphs[idx+2]
'''
if old not in test_text:
    raise RuntimeError("layout regression anchor not found")
test_path.write_text(test_text.replace(old, new, 1), encoding="utf-8")
