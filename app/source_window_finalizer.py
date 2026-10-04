from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.jd_finalizer import finalize_report


def finalize_report_by_source(
    report_path,
    output_path="generated/finalized_jobs.json",
    hours=24,
    now=None,
    source_hours=None,
):
    """Finalize each provider with the same freshness window used for discovery.

    The scheduler deliberately gives failed providers an older watermark so they
    can catch up without forcing every healthy source to replay that history. The
    ordinary finalizer accepts one ``hours`` value, so using only the global
    incremental window would rediscover a missed provider job and then reject it
    as stale during official-date verification. Split the already-filtered
    eligible report by source and apply that provider's discovery window all the
    way through final verification.

    When no provider-specific windows are supplied, preserve the original single
    finalizer call exactly.
    """
    if not source_hours:
        return finalize_report(report_path, output_path, hours=hours, now=now)

    report=json.loads(Path(report_path).read_text(encoding="utf-8"))
    results=list(report.get("results") or [])
    out=Path(output_path)
    out.parent.mkdir(parents=True,exist_ok=True)

    if not results:
        merged={"finalized":0,"held_or_rejected":0,"results":[],"rejections":[]}
        out.write_text(json.dumps(merged,indent=2),encoding="utf-8")
        return merged

    grouped={}
    for item in results:
        source=((item.get("job") or {}).get("source") or "").lower()
        grouped.setdefault(source,[]).append(item)

    finalized=[]
    rejected=[]
    with TemporaryDirectory(prefix="source-finalize-",dir=str(out.parent)) as tmp:
        tmp_root=Path(tmp)
        for index,(source,items) in enumerate(grouped.items()):
            source_window=float(source_hours.get(source,hours))
            source_window=max(source_window,0.001)
            sub_in=tmp_root/f"{index}_eligible.json"
            sub_out=tmp_root/f"{index}_finalized.json"
            sub_report=dict(report)
            sub_report["results"]=items
            sub_in.write_text(json.dumps(sub_report,indent=2),encoding="utf-8")
            result=finalize_report(str(sub_in),str(sub_out),hours=source_window,now=now)
            finalized.extend(result.get("results") or [])
            rejected.extend(result.get("rejections") or [])

    merged={
        "finalized":len(finalized),
        "held_or_rejected":len(rejected),
        "results":finalized,
        "rejections":rejected,
    }
    out.write_text(json.dumps(merged,indent=2),encoding="utf-8")
    return merged
