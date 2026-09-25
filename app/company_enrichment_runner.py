from __future__ import annotations
import argparse,json
from app.company_universe import build

def run(source_config="data/job_sources.json",registry_path=None,domain_budget=250,career_budget=250):
    return build(source_config,registry_path,domain_budget=domain_budget,career_budget=career_budget)

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Slow employer/domain/career-source enrichment")
    p.add_argument("--source-config",default="data/job_sources.json")
    p.add_argument("--registry",default=None)
    p.add_argument("--domain-budget",type=int,default=250)
    p.add_argument("--career-budget",type=int,default=250)
    a=p.parse_args()
    print(json.dumps(run(a.source_config,a.registry,a.domain_budget,a.career_budget),indent=2))
