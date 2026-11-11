from fastapi.testclient import TestClient

from main import app


def test_home_returns_200():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
