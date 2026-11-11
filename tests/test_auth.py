import jwt
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

from models import Employee
from routers.auth import COOKIE_NAME, JWT_ALGORITHM, JWT_SECRET_KEY


SIGNUP = {"name": "민지", "email": "minji@example.com", "password": "correct-horse-123"}


def test_signup_stores_bcrypt_hash_and_rejects_duplicate_in_korean(app_client):
    client, session_factory = app_client
    response = client.post("/api/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    assert response.json()["message"] == "회원가입이 완료되었습니다."
    with session_factory() as db:
        employee = db.query(Employee).filter_by(email=SIGNUP["email"]).one()
        assert employee.password_hash.startswith("$2b$12$")
        assert employee.password_hash != SIGNUP["password"]

    duplicate = client.post(
        "/api/auth/signup",
        json={**SIGNUP, "email": "MINJI@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "이미 가입된 이메일입니다."


def test_login_hides_whether_account_exists(app_client):
    client, _ = app_client
    client.post("/api/auth/signup", json=SIGNUP)

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": SIGNUP["email"], "password": "incorrect-password"},
    )
    missing_account = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "incorrect-password"},
    )

    assert wrong_password.status_code == 401
    assert missing_account.status_code == 401
    assert wrong_password.json() == missing_account.json()
    assert wrong_password.json()["detail"] == "이메일 또는 비밀번호가 올바르지 않습니다."
    assert COOKIE_NAME not in client.cookies


def test_api_login_returns_user_and_sets_http_only_jwt_cookie(app_client):
    client, _ = app_client
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 201

    response = client.post(
        "/api/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"]},
    )

    assert response.status_code == 200
    assert response.json()["name"] == SIGNUP["name"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "max-age=3600" in response.headers["set-cookie"].lower()


def test_browser_signup_login_protected_page_and_logout(app_client):
    client, _ = app_client
    assert client.get("/customers").status_code == 401
    assert client.get("/login").status_code == 200
    assert client.get("/signup").status_code == 200

    signup = client.post("/signup", data=SIGNUP, follow_redirects=False)
    assert signup.status_code == 303
    assert signup.headers["location"] == "/login?registered=true"
    assert "access_token" not in client.cookies

    login = client.post(
        "/login",
        data={"email": SIGNUP["email"], "password": SIGNUP["password"]},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/customers"
    set_cookie = login.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "max-age=3600" in set_cookie
    claims = jwt.decode(client.cookies["access_token"], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    assert claims["exp"] - claims["iat"] == 60 * 60

    customers = client.get("/customers")
    assert customers.status_code == 200
    assert "민지님 안녕하세요" in customers.text
    assert "로그아웃" in customers.text

    logout = client.post("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert "max-age=0" in logout.headers["set-cookie"].lower()
    assert "access_token" not in client.cookies
    assert client.get("/customers").status_code == 401


def test_customer_and_dashboard_apis_require_authentication(app_client):
    client, _ = app_client

    assert client.get("/api/customers").status_code == 401
    assert client.get("/api/customers/export.csv").status_code == 401
    assert client.get("/api/dashboard/sales").status_code == 401
    api_response = client.get(
        "/api/customers",
        headers={"accept": "application/json"},
    )
    assert api_response.status_code == 401
    assert api_response.json() == {"detail": "로그인이 필요합니다."}


def test_unauthenticated_browser_api_requests_redirect_to_login(app_client):
    client, _ = app_client
    browser_headers = [
        {"accept": "text/html", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"},
        {"accept": "application/json", "sec-fetch-mode": "same-origin", "sec-fetch-dest": "empty"},
    ]

    for headers in browser_headers:
        response = client.get(
            "/api/customers",
            headers=headers,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/login?login_required=true"
        login_page = client.get(response.headers["location"])
        assert "로그인 후 이용할 수 있습니다" in login_page.text


def _make_token(employee_id: int, name: str, issued_at, expires_at) -> str:
    return jwt.encode(
        {
            "sub": str(employee_id),
            "name": name,
            "iat": issued_at,
            "exp": expires_at,
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _create_test_employee(client, session_factory):
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 201
    with session_factory() as db:
        employee = db.query(Employee).filter_by(email=SIGNUP["email"]).one()
        return employee.employee_id, employee.name


def test_expired_token_redirects_browsers_and_returns_json_401_for_api(app_client):
    client, session_factory = app_client
    employee_id, name = _create_test_employee(client, session_factory)
    now = datetime.now(timezone.utc)
    expired_token = _make_token(
        employee_id,
        name,
        now - timedelta(hours=1),
        now - timedelta(seconds=1),
    )

    client.cookies.set(COOKIE_NAME, expired_token)
    browser_response = client.get(
        "/customers",
        headers={"accept": "text/html"},
        follow_redirects=False,
    )
    assert browser_response.status_code == 303
    assert browser_response.headers["location"] == "/login?session_expired=true"
    assert "max-age=0" in browser_response.headers["set-cookie"].lower()

    login_page = client.get(browser_response.headers["location"])
    assert login_page.status_code == 200
    assert "세션이 만료되었습니다" in login_page.text

    client.cookies.set(COOKIE_NAME, expired_token)
    browser_api_response = client.get(
        "/api/customers",
        headers={"accept": "application/json", "sec-fetch-mode": "same-origin"},
        follow_redirects=False,
    )
    assert browser_api_response.status_code == 303
    assert browser_api_response.headers["location"] == "/login?session_expired=true"

    client.cookies.set(COOKIE_NAME, expired_token)
    api_response = client.get(
        "/api/customers",
        headers={"accept": "application/json"},
    )
    assert api_response.status_code == 401
    assert api_response.json() == {"detail": "세션이 만료되었습니다."}
    assert "max-age=0" in api_response.headers["set-cookie"].lower()


def test_valid_token_with_five_minutes_left_is_refreshed(app_client):
    client, session_factory = app_client
    employee_id, name = _create_test_employee(client, session_factory)
    now = datetime.now(timezone.utc)
    near_expiration_token = _make_token(
        employee_id,
        name,
        now - timedelta(minutes=55),
        now + timedelta(minutes=4),
    )
    client.cookies.set(COOKIE_NAME, near_expiration_token)

    response = client.get("/customers", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert "max-age=3600" in response.headers["set-cookie"].lower()
    refreshed_cookie = SimpleCookie()
    refreshed_cookie.load(response.headers["set-cookie"])
    refreshed_claims = jwt.decode(
        refreshed_cookie[COOKIE_NAME].value,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
    )
    assert refreshed_claims["exp"] - refreshed_claims["iat"] == 60 * 60
