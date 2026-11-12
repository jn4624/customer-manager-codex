from http.cookies import SimpleCookie
from time import monotonic

from sqlalchemy import func, select

from fastapi.responses import Response

from models import Customer, Employee, HiddenCustomer
from routers.auth import COOKIE_NAME, set_auth_cookie


def _authenticate(client, session_factory):
    with session_factory() as db:
        employee = Employee(
            name="페이지 테스트",
            email="pagination@example.com",
            password_hash="test-hash",
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
        employee_id = employee.employee_id

    cookie_response = Response()
    with session_factory() as db:
        employee = db.get(Employee, employee_id)
        set_auth_cookie(cookie_response, employee)
    parsed_cookie = SimpleCookie()
    parsed_cookie.load(cookie_response.headers["set-cookie"])
    client.cookies.set(COOKIE_NAME, parsed_cookie[COOKIE_NAME].value)


def _insert_customers(session_factory, count: int):
    with session_factory() as db:
        db.execute(
            Customer.__table__.insert(),
            [
                {
                    "name": f"고객 {customer_id:05d}",
                    "email": f"customer{customer_id}@example.com",
                    "phone": None,
                    "address": f"지역 {customer_id % 10}",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "tier": "일반",
                }
                for customer_id in range(1, count + 1)
            ],
        )
        db.commit()


def test_customer_api_uses_twenty_row_pages_and_serves_page_500_under_one_second(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    _insert_customers(session_factory, 10_000)

    started_at = monotonic()
    response = client.get("/api/customers?page=500")
    elapsed = monotonic() - started_at

    assert response.status_code == 200
    assert len(response.json()) == 20
    assert response.json()[0]["name"] == "고객 09981"
    assert response.json()[-1]["name"] == "고객 10000"
    assert response.headers["x-total-count"] == "10000"
    assert elapsed < 1.0
    assert client.get("/api/customers?page=1&page_size=100").status_code == 422


def test_hidden_customers_are_excluded_from_api_page_and_dashboard_count(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    _insert_customers(session_factory, 21)
    with session_factory() as db:
        hidden_customer_id = db.scalar(
            select(Customer.customer_id).order_by(Customer.customer_id.desc())
        )
        db.add(HiddenCustomer(customer_id=hidden_customer_id))
        db.commit()

    first_page = client.get("/api/customers?page=1")
    second_page = client.get("/api/customers?page=2")
    dashboard = client.get("/api/dashboard/sales")

    assert first_page.status_code == 200
    assert len(first_page.json()) == 20
    assert len(second_page.json()) == 0
    assert first_page.headers["x-total-count"] == "20"
    assert dashboard.json()["customer_count"] == 20
    assert hidden_customer_id not in {row["customer_id"] for row in first_page.json()}


def test_browser_customer_page_paginates_twenty_rows_and_excludes_hidden(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    _insert_customers(session_factory, 21)
    with session_factory() as db:
        last_customer_id = db.scalar(
            select(func.max(Customer.customer_id))
        )
        db.add(HiddenCustomer(customer_id=last_customer_id))
        db.commit()

    page = client.get("/customers?page=1")

    assert page.status_code == 200
    assert "전체 고객 <strong>20</strong>명" in page.text
    assert "1 / 1 페이지" in page.text
    assert 'class="page-number active" href="/customers?page=1" aria-current="page">1</a>' in page.text
    assert "고객 00021" not in page.text


def test_customer_page_shows_at_most_ten_page_numbers_per_group(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    _insert_customers(session_factory, 221)

    first_page = client.get("/customers?page=1")
    eleventh_page = client.get("/customers?page=11")

    assert first_page.text.count('class="page-number') == 10
    assert 'aria-label="다음 10페이지"' in first_page.text
    assert 'href="/customers?page=11" aria-label="다음 10페이지"' in first_page.text
    assert 'href="/customers?page=12" aria-label="마지막 페이지"' in first_page.text
    assert eleventh_page.text.count('class="page-number') == 2
    assert 'href="/customers?page=11" aria-current="page">11</a>' in eleventh_page.text
    assert 'href="/customers?page=12"' in eleventh_page.text
    assert 'href="/customers?page=1" aria-label="처음 페이지"' in eleventh_page.text
    assert 'href="/customers?page=12" aria-label="마지막 페이지"' in eleventh_page.text
