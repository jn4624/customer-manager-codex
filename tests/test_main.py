def test_home_renders_shared_layout_and_health_endpoint(app_client):
    client, _ = app_client
    home = client.get("/")
    health = client.get("/health")

    assert home.status_code == 200
    assert "text/html" in home.headers["content-type"]
    assert 'href="/" class="active" aria-current="page">홈</a>' in home.text
    assert 'href="/customers">고객 목록</a>' in home.text
    assert "로그인하기" in home.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
