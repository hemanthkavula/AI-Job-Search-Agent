from app.job_ledger import seen_or_submitted

def _ledger(status):
 return {"jobs":{"lever:acme:1":{"application_status":status,"external_id":"lever:acme:1","source":"lever"}},"aliases":{}}

def _job():return {"external_id":"lever:acme:1","source":"lever","company":"Acme","title":"Data Engineer"}

def test_confirmed_submission_is_terminal():
 assert seen_or_submitted(_job(),_ledger("SUBMITTED_CONFIRMED"))[0] is True

def test_unconfirmed_submission_can_be_retried_safely():
 assert seen_or_submitted(_job(),_ledger("SUBMISSION_UNCONFIRMED"))[0] is False

def test_blocked_application_can_be_revisited_after_external_challenge():
 assert seen_or_submitted(_job(),_ledger("BLOCKED"))[0] is False
