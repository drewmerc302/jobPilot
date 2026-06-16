"""Application-status visibility + follow-up queue.

Locks two fixes ported from jobTracker:
- 'interested' jobs stay visible in the applications view after the listing
  is delisted (and sort below 'applied', above 'new').
- Overdue follow-ups exclude jobs whose listing has been delisted.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobpilot.db import Database  # noqa: E402


def _add_job(db, job_id, company="Acme", title="Engineering Manager"):
    db.upsert_job(
        id=job_id,
        company=company,
        title=title,
        url=f"https://example.com/{job_id}",
        scraped_at=datetime.now(timezone.utc),
        source="greenhouse",
    )
    db.insert_match(job_id=job_id, relevance_score=0.9, match_reason="test")


def test_interested_job_visible_after_delisting(tmp_path):
    db = Database(tmp_path / "test.db")
    _add_job(db, "Acme:1")
    db.set_application_status("Acme:1", "interested")
    db.close_job("Acme:1")  # listing delisted

    ids = [a["job_id"] for a in db.get_all_applications()]
    assert "Acme:1" in ids  # interested survives delisting


def test_new_job_hidden_after_delisting(tmp_path):
    db = Database(tmp_path / "test.db")
    _add_job(db, "Acme:2")
    db.close_job("Acme:2")  # untouched 'new' job, then delisted

    ids = [a["job_id"] for a in db.get_all_applications()]
    assert "Acme:2" not in ids


def test_interested_sorts_below_applied_above_new(tmp_path):
    db = Database(tmp_path / "test.db")
    for jid, status in [
        ("Acme:applied", "applied"),
        ("Acme:interested", "interested"),
        ("Acme:new", None),
    ]:
        _add_job(db, jid)
        if status:
            db.set_application_status(jid, status)

    order = [a["job_id"] for a in db.get_all_applications()]
    assert (
        order.index("Acme:applied")
        < order.index("Acme:interested")
        < order.index("Acme:new")
    )


def test_overdue_follow_up_excludes_delisted(tmp_path):
    db = Database(tmp_path / "test.db")
    for jid in ("Acme:open", "Acme:closed"):
        _add_job(db, jid)
        db.set_application_status(jid, "applied")
        db.set_follow_up_date(jid, "2000-01-01")  # overdue
    db.close_job("Acme:closed")

    overdue_ids = [r["job_id"] for r in db.get_overdue_follow_ups()]
    assert "Acme:open" in overdue_ids
    assert "Acme:closed" not in overdue_ids
