from http.cookies import SimpleCookie

from fastapi.responses import Response
from sqlalchemy import func, select

from models import Customer, Employee, HiddenCustomer, Order, Product
from routers.auth import COOKIE_NAME, set_auth_cookie


def _authenticate(client, session_factory):
    with session_factory() as db:
        employee = Employee(name="고객 테스트", email="crud@example.com")
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


def test_customer_registration_duplicate_hidden_email_reuse_and_edit_limits(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)

    created = client.post(
        "/api/customers",
        json={
            "name": "홍길동",
            "email": "gil@example.com",
            "phone": "010-1111-2222",
            "address": "서울",
            "tier": "VIP",
        },
    )
    assert created.status_code == 201
    assert created.headers["x-customer-page"] == "1"
    customer = created.json()
    assert customer["email"] == "gil@example.com"
    assert customer["tier"] == "VIP"

    duplicate = client.post(
        "/api/customers",
        json={"name": "중복", "email": "GIL@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "이미 등록된 고객입니다."

    edit = client.patch(
        f"/api/customers/{customer['customer_id']}",
        json={"name": "홍길동 수정", "phone": "010-3333-4444", "address": "부산"},
    )
    assert edit.status_code == 200
    assert edit.json()["name"] == "홍길동 수정"
    assert edit.json()["phone"] == "010-3333-4444"
    assert edit.json()["email"] == "gil@example.com"
    assert edit.json()["created_at"] == customer["created_at"]
    assert edit.json()["tier"] == "VIP"

    forbidden_edit = client.patch(
        f"/api/customers/{customer['customer_id']}",
        json={"email": "changed@example.com", "tier": "일반", "created_at": "changed"},
    )
    assert forbidden_edit.status_code == 422

    with session_factory() as db:
        employee = db.scalar(select(Employee).where(Employee.email == "crud@example.com"))
        product = Product(name="테스트 상품", unit_price=10.0, stock_quantity=1)
        db.add(product)
        db.flush()
        db.add(
            Order(
                customer_id=customer["customer_id"],
                product_id=product.product_id,
                employee_id=employee.employee_id,
                order_date="2026-01-01",
                quantity=1,
                unit_price=10.0,
                status="완료",
                total_amount=10.0,
            )
        )
        db.commit()
        customer_before_hide = db.get(Customer, customer["customer_id"])
        customer_values_before_hide = {
            field: getattr(customer_before_hide, field)
            for field in ("name", "email", "phone", "address", "created_at", "tier")
        }

    hidden = client.delete(f"/api/customers/{customer['customer_id']}")
    assert hidden.status_code == 204
    assert client.get(f"/api/customers/{customer['customer_id']}").status_code == 404
    with session_factory() as db:
        archived = db.get(Customer, customer["customer_id"])
        hidden_record = db.get(HiddenCustomer, customer["customer_id"])
        assert archived is not None
        assert {
            field: getattr(archived, field) for field in customer_values_before_hide
        } == customer_values_before_hide
        assert hidden_record is not None
        assert db.scalar(select(func.count(Order.order_id))) == 1

    reused = client.post(
        "/api/customers",
        json={"name": "새 고객", "email": "gil@example.com"},
    )
    assert reused.status_code == 201
    assert reused.json()["customer_id"] == customer["customer_id"]
    assert reused.json()["email"] == "gil@example.com"
    assert reused.json()["name"] == "새 고객"


def test_customer_browser_register_edit_and_hide_flow(app_client):
    client, session_factory = app_client
    _authenticate(client, session_factory)

    page = client.get("/customers")
    assert 'id="customer-create-dialog"' in page.text
    assert 'id="open-customer-create" type="button">고객 등록</button>' in page.text
    assert page.text.index('id="open-customer-create"') < page.text.index('id="delete-selected-button"')
    assert 'id="submit-customer-create" type="submit">등록</button>' in page.text
    assert 'id="cancel-customer-create" class="secondary" type="button">취소</button>' in page.text
    assert page.text.index('id="submit-customer-create"') < page.text.index('id="cancel-customer-create"')
    assert 'fetch("/api/customers"' in page.text
    assert client.get("/customers/new").status_code == 422

    duplicate = client.post(
        "/api/customers",
        json={"name": "첫 고객", "email": "first@example.com"},
    )
    assert duplicate.status_code == 201
    customer_list = client.get(f"/customers?page={duplicate.headers['x-customer-page']}")
    assert "첫 고객" in customer_list.text
    assert f'class="clickable-row" data-href="/customers/' in customer_list.text
    assert '<td><a href="/customers/' not in customer_list.text
    assert 'name="customer_ids"' in customer_list.text
    assert 'id="delete-selected-button"' in customer_list.text
    with session_factory() as db:
        customer_id = db.scalar(select(Customer.customer_id).where(Customer.email == "first@example.com"))
    detail_url = f"/customers/{customer_id}"

    duplicate_email = client.post(
        "/api/customers",
        json={"name": "중복 고객", "email": "FIRST@example.com"},
    )
    assert duplicate_email.status_code == 409
    assert duplicate_email.json()["detail"] == "이미 등록된 고객입니다."

    with session_factory() as db:
        employee = db.scalar(select(Employee).where(Employee.email == "crud@example.com"))
        product = Product(name="주문 이력 상품", unit_price=25.0, stock_quantity=3)
        db.add(product)
        db.flush()
        db.add(
            Order(
                customer_id=customer_id,
                product_id=product.product_id,
                employee_id=employee.employee_id,
                order_date="2026-10-01",
                quantity=2,
                unit_price=25.0,
                status="완료",
                total_amount=50.0,
            )
        )
        db.commit()

    detail_page = client.get(detail_url)
    assert detail_page.status_code == 200
    assert "숨김 삭제" not in detail_page.text
    assert 'id="email" value="first@example.com" disabled' in detail_page.text
    assert 'id="name" name="name" value="첫 고객" required maxlength="200" disabled' in detail_page.text
    assert 'id="save-button" type="submit" form="customer-edit-form" hidden disabled' in detail_page.text
    assert 'id="edit-button" type="button">수정</button>' in detail_page.text
    assert 'method: "PATCH"' in detail_page.text
    assert detail_page.text.index('id="save-button"') < detail_page.text.index('id="cancel-button"')
    assert detail_page.text.index('class="detail-actions customer-detail-actions"') < detail_page.text.index(
        'aria-labelledby="order-history-title"'
    )
    assert "주문 이력 상품" in detail_page.text
    assert "50원" in detail_page.text

    edit = client.post(
        f"/customers/{customer_id}/edit",
        data={"name": "첫 고객 수정", "phone": "010-5555-6666", "address": "대전"},
        follow_redirects=False,
    )
    assert edit.status_code == 303
    assert client.get(f"/api/customers/{customer_id}").json()["name"] == "첫 고객 수정"
    assert 'value="첫 고객 수정"' in client.get(detail_url).text

    hide = client.post(
        "/customers/hide-selected",
        data={"customer_ids": str(customer_id)},
        follow_redirects=False,
    )
    assert hide.status_code == 303
    assert hide.headers["location"] == "/customers"
    assert client.get(f"/api/customers/{customer_id}").status_code == 404
    assert "첫 고객 수정" not in client.get("/customers").text
    with session_factory() as db:
        hidden_customer = db.get(Customer, customer_id)
        assert hidden_customer is not None
        assert hidden_customer.email == "first@example.com"
        assert db.scalar(select(func.count(Order.order_id))) == 1
