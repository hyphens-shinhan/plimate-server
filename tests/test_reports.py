import uuid


def test_confirm_attendance_no_report(client):
    """Confirming attendance for a nonexistent report should 404 (or 500 from .single())."""
    fake_id = str(uuid.uuid4())
    r = client.patch(f"/api/v1/reports/council/{fake_id}/confirm")
    assert r.status_code in (404, 500)


def test_reject_attendance_no_report(client):
    """Rejecting attendance for a nonexistent report should 404 (or 500 from .single())."""
    fake_id = str(uuid.uuid4())
    r = client.patch(f"/api/v1/reports/council/{fake_id}/reject")
    assert r.status_code in (404, 500)
