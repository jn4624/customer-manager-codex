from html import unescape
from http.cookies import SimpleCookie
import re
from urllib.parse import parse_qs, urlsplit

from fastapi.responses import Response
from sqlalchemy import select

from models import Customer, Employee
from routers.auth import COOKIE_NAME, set_auth_cookie


def _authenticate(client, session_factory):
    with session_factory() as db:
        employee = Employee(name="검색 테스트", email="search@example.com")
        db.add(employee)
        db.commit()
        db.refresh(employee)
        employee_id = employee.employee_id

    response = Response()
    with session_factory() as db:
        set_auth_cookie(response, db.get(Employee, employee_id))
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    client.cookies.set(COOKIE_NAME, cookie[COOKIE_NAME].value)


def _add_customer(session_factory, *, name, email, address, tier="일반"):
    with session_factory() as db:
        customer = Customer(
            name=name,
            email=email,
            address=address,
            tier=tier,
            created_at="2026-01-01T00:00:00+00:00",
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer.customer_id


def test_search_ignores_korean_name_spaces_and_escapes_like_wildcards(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    spaced_name_id = _add_customer(
        session_factory,
        name="이 민수",
        email="literal%_marker@example.com",
        address="서울특별시 강남구",
    )
    compact_name_id = _add_customer(
        session_factory,
        name="이민수",
        email="ordinary@example.com",
        address="부산광역시 해운대구",
    )
    _add_customer(
        session_factory,
        name="다른 고객",
        email="literalAXmarker@example.com",
        address="서울특별시 종로구",
    )

    compact_search = client.get("/api/customers", params={"q": "이민수"})
    spaced_search = client.get("/customers", params={"q": "이 민수"})
    wildcard_search = client.get("/api/customers", params={"q": "%_"})
    case_insensitive_email_search = client.get(
        "/api/customers", params={"q": "LITERAL%_MARKER@EXAMPLE.COM"}
    )

    assert compact_search.status_code == 200
    assert {row["customer_id"] for row in compact_search.json()} == {
        spaced_name_id,
        compact_name_id,
    }
    assert spaced_search.status_code == 200
    assert "이 민수" in spaced_search.text
    assert "이민수" in spaced_search.text
    assert wildcard_search.status_code == 200
    assert [row["customer_id"] for row in wildcard_search.json()] == [spaced_name_id]
    assert [row["customer_id"] for row in case_insensitive_email_search.json()] == [
        spaced_name_id
    ]


def test_tier_region_filters_render_results_and_persist_across_pages(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    matching_ids = {
        _add_customer(
            session_factory,
            name=f"김민수 {index:02d}",
            email=f"kim{index:02d}@example.com",
            address="서울특별시 강남구 테헤란로",
            tier="VIP",
        )
        for index in range(21)
    }
    _add_customer(
        session_factory,
        name="김민수 제외",
        email="excluded@example.com",
        address="부산광역시 해운대구",
        tier="일반",
    )

    first_page = client.get(
        "/customers",
        params={"q": "김민수", "tier": "VIP", "region": "서울특별시"},
    )
    api_filtered = client.get(
        "/api/customers",
        params={"q": "김민수", "tier": "VIP", "region": "서울특별시"},
    )

    assert first_page.status_code == 200
    assert api_filtered.status_code == 200
    assert api_filtered.headers["x-total-count"] == "21"
    assert {row["customer_id"] for row in api_filtered.json()} <= matching_ids
    assert len(api_filtered.json()) == 20
    assert "검색 결과 <strong>21</strong>명" in first_page.text
    assert 'id="customer-tier-filter" name="tier">' in first_page.text
    assert '<option value="VIP" selected>VIP</option>' in first_page.text
    assert '<option value="서울특별시" selected>서울특별시</option>' in first_page.text
    assert "김민수 제외" not in first_page.text

    next_link_match = re.search(
        r'<a class="page-step" href="([^"]+)" rel="next"', first_page.text
    )
    assert next_link_match is not None
    next_url = unescape(next_link_match.group(1))
    next_params = parse_qs(urlsplit(next_url).query)
    assert next_params == {
        "page": ["2"],
        "q": ["김민수"],
        "tier": ["VIP"],
        "region": ["서울특별시"],
    }

    second_page = client.get(next_url)
    assert second_page.status_code == 200
    assert "김민수 20" in second_page.text
    assert "김민수 00" not in second_page.text
    assert 'id="customer-search-query" name="q" type="search" value="김민수"' in second_page.text
    assert '<option value="VIP" selected>VIP</option>' in second_page.text
    assert '<option value="서울특별시" selected>서울특별시</option>' in second_page.text
    assert "2 / 2 페이지" in second_page.text

    no_results = client.get(
        "/customers",
        params={"q": "없는 이름", "tier": "VIP", "region": "서울특별시"},
    )
    assert "검색 결과가 없습니다." in no_results.text
    assert "<table>" not in no_results.text


def test_customer_name_whitespace_is_rejected_and_checkbox_space_does_not_navigate(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)
    customer_id = _add_customer(
        session_factory,
        name="원래 이름",
        email="unchanged@example.com",
        address="서울특별시 강남구",
    )

    api_edit = client.patch(f"/api/customers/{customer_id}", json={"name": "   "})
    form_edit = client.post(
        f"/customers/{customer_id}/edit",
        data={"name": "   ", "phone": "", "address": ""},
    )
    with session_factory() as db:
        saved_name = db.scalar(
            select(Customer.name).where(Customer.customer_id == customer_id)
        )
    customer_page = client.get("/customers")

    assert api_edit.status_code == 422
    assert form_edit.status_code == 422
    assert saved_name == "원래 이름"
    assert 'row.addEventListener("keydown", (event) => {\n      if (event.target.closest("a, button, input, select, textarea")) return;' in customer_page.text
