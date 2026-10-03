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
