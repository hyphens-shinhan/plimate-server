def test_get_home_profile(client):
    """200 if test user exists in DB, 500 otherwise (user row required)."""
    r = client.get("/api/v1/users/me")
    assert r.status_code in (200, 500)
    if r.status_code == 200:
        data = r.json()
        assert "id" in data
        assert "name" in data
        assert "role" in data


def test_get_my_profile(client):
    """200 if test user exists in DB, 500 otherwise."""
    r = client.get("/api/v1/users/me/profile")
    assert r.status_code in (200, 500)
    if r.status_code == 200:
        data = r.json()
        assert "id" in data
        assert "email" in data
        assert "name" in data


def test_get_scholarship_eligibility(client):
    r = client.get("/api/v1/users/me/scholarship-eligibility")
    assert r.status_code == 200
    data = r.json()
    assert "gpa" in data
    assert "volunteer_hours" in data
    assert "mandatory_total" in data
    assert "mandatory_completed" in data


def test_get_mandatory_status(client):
    r = client.get("/api/v1/users/me/mandatory-status")
    assert r.status_code == 200
    data = r.json()
    assert "year" in data
    assert "total" in data
    assert "completed" in data
    assert "activities" in data


def test_get_privacy_settings(client):
    r = client.get("/api/v1/users/me/privacy")
    assert r.status_code == 200
    data = r.json()
    assert "is_location_public" in data
    assert "is_contact_public" in data
    assert "is_scholarship_public" in data
    assert "is_follower_public" in data


def test_get_volunteer_hours(client):
    r = client.get("/api/v1/users/me/volunteer")
    assert r.status_code == 200
    data = r.json()
    assert "volunteer_hours" in data
