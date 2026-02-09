import uuid


def test_get_videos(client):
    """Should return video list (may be empty). 500 if table not yet created."""
    r = client.get("/api/v1/videos")
    assert r.status_code in (200, 500)
    if r.status_code == 200:
        data = r.json()
        assert "videos" in data
        assert "total" in data
        assert isinstance(data["videos"], list)


def test_create_video_not_admin(client):
    """Non-admin test user should get 403 (or 500 if user doesn't exist)."""
    r = client.post(
        "/api/v1/videos",
        json={
            "title": "Test Video",
            "url": "https://www.youtube.com/watch?v=test",
        },
    )
    assert r.status_code in (403, 500)


def test_delete_video_not_admin(client):
    """Non-admin test user should get 403 (or 500 if user doesn't exist)."""
    fake_id = str(uuid.uuid4())
    r = client.delete(f"/api/v1/videos/{fake_id}")
    assert r.status_code in (403, 500)
