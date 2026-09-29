import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient


def register_and_login(client: TestClient, email: str = "ana@example.com") -> str:
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password-123"},
    )
    assert registration.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password-123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def idempotent(token: str, key: uuid.UUID | None = None) -> dict[str, str]:
    return auth(token) | {"Idempotency-Key": str(key or uuid.uuid4())}


def test_account_category_and_tenant_contracts(api_client: TestClient) -> None:
    first_token = register_and_login(api_client)
    account_key = uuid.uuid4()
    account_payload = {"name": "Banco Principal", "type": "BANK", "opening_balance": "100.00"}
    created = api_client.post(
        "/api/v1/accounts",
        json=account_payload,
        headers=idempotent(first_token, account_key),
    )
    replay = api_client.post(
        "/api/v1/accounts",
        json=account_payload,
        headers=idempotent(first_token, account_key),
    )
    assert created.status_code == replay.status_code == 201
    assert created.json() == replay.json()
    assert created.json()["balance"] == "100.00"
    account_id = created.json()["id"]

    category_key = uuid.uuid4()
    category_payload = {"name": "Mascotas", "type": "EXPENSE"}
    category = api_client.post(
        "/api/v1/categories",
        json=category_payload,
        headers=idempotent(first_token, category_key),
    )
    category_replay = api_client.post(
        "/api/v1/categories",
        json=category_payload,
        headers=idempotent(first_token, category_key),
    )
    assert category.status_code == 201
    assert category.json() == category_replay.json()
    category_id = category.json()["id"]
    assert api_client.patch(
        f"/api/v1/categories/{category_id}",
        json={"status": "INACTIVE"},
        headers=auth(first_token),
    ).json()["status"] == "INACTIVE"
    assert api_client.patch(
        f"/api/v1/categories/{category_id}",
        json={"status": "ACTIVE"},
        headers=auth(first_token),
    ).json()["status"] == "ACTIVE"

    second_token = register_and_login(api_client, "other@example.com")
    foreign_patch = api_client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"name": "Cuenta ajena"},
        headers=auth(second_token),
    )
    assert foreign_patch.status_code == 404
    assert api_client.get("/api/v1/accounts", headers=auth(second_token)).json() == []


def test_complete_movement_balance_history_void_and_deactivation_flow(api_client: TestClient) -> None:
    token = register_and_login(api_client)
    categories = api_client.get("/api/v1/categories", headers=auth(token)).json()
    salary = next(item for item in categories if item["name"] == "Salario")
    market = next(item for item in categories if item["name"] == "Mercado")

    account = api_client.post(
        "/api/v1/accounts",
        json={"name": "Efectivo", "type": "CASH", "opening_balance": "100.00"},
        headers=idempotent(token),
    )
    assert account.status_code == 201
    account_id = account.json()["id"]
    today = date.today().isoformat()

    income_key = uuid.uuid4()
    income_payload = {
        "type": "INCOME",
        "account_id": account_id,
        "category_id": salary["id"],
        "amount": "50.00",
        "date": today,
        "note": "Ingreso",
    }
    income = api_client.post(
        "/api/v1/movements",
        json=income_payload,
        headers=idempotent(token, income_key),
    )
    income_replay = api_client.post(
        "/api/v1/movements",
        json=income_payload,
        headers=idempotent(token, income_key),
    )
    assert income.status_code == income_replay.status_code == 201
    assert income.json() == income_replay.json()
    assert income.json()["new_balance"] == "150.00"

    expense = api_client.post(
        "/api/v1/movements",
        json={
            "type": "EXPENSE",
            "account_id": account_id,
            "category_id": market["id"],
            "amount": "25.00",
            "date": today,
            "note": "Mercado",
        },
        headers=idempotent(token),
    )
    assert expense.status_code == 201
    assert expense.json()["new_balance"] == "125.00"
    expense_id = expense.json()["movement"]["id"]

    balance = api_client.get("/api/v1/balance", headers=auth(token))
    assert balance.status_code == 200
    assert balance.json()["consolidated_balance"] == "125.00"
    assert balance.json()["accounts"][0]["balance"] == "125.00"

    insufficient = api_client.post(
        "/api/v1/movements",
        json={
            "type": "EXPENSE",
            "account_id": account_id,
            "category_id": market["id"],
            "amount": "125.01",
            "date": today,
        },
        headers=idempotent(token),
    )
    assert insufficient.status_code == 422
    assert "Saldo insuficiente" in insufficient.json()["detail"][0]["message"]

    future = api_client.post(
        "/api/v1/movements",
        json={
            "type": "INCOME",
            "account_id": account_id,
            "category_id": salary["id"],
            "amount": "1.00",
            "date": (date.today() + timedelta(days=1)).isoformat(),
        },
        headers=idempotent(token),
    )
    assert future.status_code == 422
    assert future.json()["detail"][0]["field"] == "date"

    history = api_client.get(
        "/api/v1/movements",
        params={"account_id": account_id, "category_id": market["id"], "page_size": 100},
        headers=auth(token),
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["account"]["name"] == "Efectivo"
    assert history.json()["items"][0]["category"]["name"] == "Mercado"

    voided = api_client.post(f"/api/v1/movements/{expense_id}/void", headers=auth(token))
    assert voided.status_code == 200
    assert voided.json()["new_balance"] == "150.00"
    assert voided.json()["negative_balance_warning"] is False
    assert api_client.post(f"/api/v1/movements/{expense_id}/void", headers=auth(token)).status_code == 422

    deactivated = api_client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"status": "INACTIVE"},
        headers=auth(token),
    )
    assert deactivated.status_code == 200
    assert api_client.get("/api/v1/balance", headers=auth(token)).json()["consolidated_balance"] == "0.00"
    inactive_movement = api_client.post(
        "/api/v1/movements",
        json={
            "type": "INCOME",
            "account_id": account_id,
            "category_id": salary["id"],
            "amount": "1.00",
            "date": today,
        },
        headers=idempotent(token),
    )
    assert inactive_movement.status_code == 422
    assert inactive_movement.json()["detail"][0]["field"] == "account_id"


def test_error_contract_and_openapi_routes(api_client: TestClient) -> None:
    token = register_and_login(api_client)
    invalid_money = api_client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "type": "CASH", "opening_balance": 10.0},
        headers=idempotent(token),
    )
    assert invalid_money.status_code == 422
    assert invalid_money.json()["detail"][0]["field"] == "opening_balance"
    assert "texto decimal" in invalid_money.json()["detail"][0]["message"]

    paths = api_client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/users/me",
        "/api/v1/accounts",
        "/api/v1/accounts/{account_id}",
        "/api/v1/categories",
        "/api/v1/categories/{category_id}",
        "/api/v1/movements",
        "/api/v1/movements/{movement_id}/void",
        "/api/v1/balance",
    }
    assert expected <= set(paths)
