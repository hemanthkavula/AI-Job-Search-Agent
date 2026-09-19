from datetime import datetime, timedelta, timezone

from app.job_ledger import _retry_due, retry_metadata


def test_retry_metadata_uses_bounded_backoff():
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    row = {}

    first = retry_metadata(row, "application", now)
    assert first["application_retry_count"] == 1
    assert first["application_retry_after"] == (now + timedelta(minutes=60)).isoformat()
    assert first["application_retry_exhausted"] is False

    second = retry_metadata(first, "application", now)
    assert second["application_retry_count"] == 2
    assert second["application_retry_after"] == (now + timedelta(minutes=120)).isoformat()

    third = retry_metadata(second, "application", now)
    assert third["application_retry_count"] == 3
    assert third["application_retry_after"] is None
    assert third["application_retry_exhausted"] is True


def test_retry_due_respects_backoff_and_limit():
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    row = {
        "resume_retry_count": 1,
        "resume_retry_after": (now + timedelta(minutes=30)).isoformat(),
    }
    assert _retry_due(row, "resume", now) is False
    assert _retry_due(row, "resume", now + timedelta(minutes=31)) is True

    row["resume_retry_count"] = 3
    row["resume_retry_after"] = None
    assert _retry_due(row, "resume", now + timedelta(days=1)) is False
