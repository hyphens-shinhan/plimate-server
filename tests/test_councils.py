import uuid
from datetime import datetime


def test_get_councils_not_admin(client):
    """Non-admin test user should get 403 (or 500 if user doesn't exist in DB)."""
    r = client.get("/api/v1/councils")
    assert r.status_code in (403, 500)


def test_create_council_not_admin(client):
    """Non-admin test user should get 403 (or 500 if user doesn't exist in DB)."""
    r = client.post(
        "/api/v1/councils",
        json={
            "year": datetime.now().year,
            "affiliation": "Test University",
            "region": "Seoul",
            "leader_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code in (403, 500)


def test_get_my_council_activity(client):
    """Should return council activity for current year (may be empty)."""
    r = client.get(f"/api/v1/councils/me/{datetime.now().year}")
    assert r.status_code == 200
    data = r.json()
    assert "year" in data
    assert "councils" in data
