from app.cost_optimizer import jd_hash,resume_profile,similarity,find_reusable

def test_jd_hash_normalizes_whitespace_and_case():
 assert jd_hash("Python   SQL") == jd_hash("python sql")

def test_resume_profile_routes_cloud_stack():
 profile,scores=resume_profile("Build AWS S3 Glue Redshift data pipelines")
 assert profile=="aws" and scores["aws"]>=3

def test_similarity_and_reuse_threshold():
 a="Python SQL Spark Databricks AWS S3 Glue Redshift Kafka data pipelines"
 b="Python SQL Spark Databricks AWS S3 Glue Redshift Kafka data pipelines"
 assert similarity(a,b)==1.0
 hit=find_reusable(a,{"jobs":{"x":{"description":b,"resume_path":"resume.docx"}}},.92)
 assert hit and hit["resume_path"]=="resume.docx"
