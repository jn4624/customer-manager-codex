def test_home_returns_200(app_client):
    client, _ = app_client
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
