def test_nearby_users(client):
    """Should return 400 if test user has no location, or 200 with results."""
    r = client.get("/api/v1/networking/nearby")
    assert r.status_code in (200, 400)
    if r.status_code == 400:
        assert "location" in r.json()["detail"].lower()
    else:
        data = r.json()
        assert "users" in data
        assert "total" in data
        assert "center_lat" in data
        assert "center_lng" in data


def test_friend_recommendations(client):
    r = client.get("/api/v1/networking/recommendations")
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    assert "total" in data


def test_my_friends(client):
    r = client.get("/api/v1/networking/friends")
    assert r.status_code == 200
    data = r.json()
    assert "friends" in data
    assert "total" in data
