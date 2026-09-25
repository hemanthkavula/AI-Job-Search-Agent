from __future__ import annotations
import argparse,json
from app.company_universe import build

def run(source_config="data/job_sources.json",registry_path=None,domain_budget=250,career_budget=250,retry_days=7):
    return build(source_config,registry_path,domain_budget=domain_budget,career_budget=career_budget,retry_days=retry_days)

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Slow employer/domain/career-source enrichment")
    p.add_argument("--source-config",default="data/job_sources.json")
    p.add_argument("--registry",default=None)
    p.add_argument("--domain-budget",type=int,default=250)
    p.add_argument("--career-budget",type=int,default=250)
    p.add_argument("--retry-days",type=int,default=7)
    a=p.parse_args()
    print(json.dumps(run(a.source_config,a.registry,a.domain_budget,a.career_budget,a.retry_days),indent=2))
