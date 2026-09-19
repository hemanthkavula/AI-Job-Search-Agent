from __future__ import annotations
import hashlib,json,re
from pathlib import Path

CACHE_PATH=Path("generated/cost_optimizer_cache.json")
PROFILE_HINTS={
 "aws":("aws","s3","glue","redshift","emr","lambda","kinesis"),
 "azure":("azure","adf","synapse","adls","event hub"),
 "databricks":("databricks","delta lake","unity catalog"),
 "snowflake":("snowflake","dbt"),
 "gcp":("gcp","google cloud","bigquery"),
 "streaming":("kafka","kinesis","event hub","flink","streaming"),
 "healthcare":("healthcare","hipaa","claims","ehr"),
 "financial":("financial","trading","market data","risk","compliance"),
}

def jd_hash(description):
 text=re.sub(r"\s+"," ",(description or "").strip().lower())
 return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None

def resume_profile(description):
 text=(description or "").lower();scores={k:sum(term in text for term in terms) for k,terms in PROFILE_HINTS.items()}
 best=max(scores,key=scores.get) if scores and max(scores.values()) else "general"
 return best,scores

def _tokens(text):
 return set(re.findall(r"[a-z0-9+#.]{2,}",(text or "").lower()))

def similarity(a,b):
 x,y=_tokens(a),_tokens(b)
 return len(x&y)/len(x|y) if x and y else 0.0

def load_cache(path=CACHE_PATH):
 try:return json.loads(Path(path).read_text(encoding="utf-8"))
 except Exception:return {"version":1,"jobs":{}}

def save_cache(cache,path=CACHE_PATH):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(cache,indent=2),encoding="utf-8")

def find_reusable(description,cache=None,threshold=.92):
 cache=cache or load_cache();best=None
 for key,row in (cache.get("jobs") or {}).items():
  score=similarity(description,row.get("description",""))
  if score>=threshold and (best is None or score>best["similarity"]):best={"key":key,"similarity":score,**row}
 return best

def remember(description,**metadata):
 key=jd_hash(description)
 if not key:return None
 cache=load_cache();cache.setdefault("jobs",{})[key]={"description":description,"profile":resume_profile(description)[0],**metadata};save_cache(cache);return key
