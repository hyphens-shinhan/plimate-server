import uuid


def test_search_mentors(client):
    r = client.get("/api/v1/mentoring/mentors")
    assert r.status_code == 200
    data = r.json()
    assert "mentors" in data
    assert "total" in data


def test_get_mentor_profile_me(client):
    """200 if test user is a mentor, 403 if not, 404 if user doesn't exist."""
    r = client.get("/api/v1/mentoring/profile/me")
    assert r.status_code in (200, 403, 404)


def test_get_survey(client):
    """Should return 200 if test user has a survey, 404 otherwise."""
    r = client.get("/api/v1/mentoring/survey/me")
    assert r.status_code in (200, 404)


def test_get_recommendations(client):
    """Should return 200 if test user has a survey, 404 otherwise."""
    r = client.get("/api/v1/mentoring/recommendations")
    assert r.status_code in (200, 404)


def test_get_mentor_profile_nonexistent(client):
    fake_id = str(uuid.uuid4())
    r = client.get(f"/api/v1/mentoring/mentors/{fake_id}")
    assert r.status_code == 404
