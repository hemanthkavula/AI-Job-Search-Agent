from __future__ import annotations
import argparse,json
from app.company_universe import build

def run(source_config="data/job_sources.json",registry_path=None):
    return build(source_config,registry_path)

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Slow employer/domain/career-source enrichment")
    p.add_argument("--source-config",default="data/job_sources.json")
    p.add_argument("--registry",default=None)
    a=p.parse_args()
    print(json.dumps(run(a.source_config,a.registry),indent=2))
