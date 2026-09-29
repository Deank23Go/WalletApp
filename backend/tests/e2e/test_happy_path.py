from __future__ import annotations

import uuid
from datetime import date

import httpx


def _register_and_login(client: httpx.Client) -> str:
    assert client.post(
        "/api/v1/auth/register",
        json={"email": "happy@example.com", "password": "password-123"},
    ).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "happy@example.com", "password": "password-123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _headers(token: str, *, idempotent: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotent:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    return headers


def test_complete_financial_journey_over_real_http(e2e_client: httpx.Client) -> None:
    token = _register_and_login(e2e_client)
    categories = e2e_client.get("/api/v1/categories", headers=_headers(token)).json()
    salary = next(item for item in categories if item["name"] == "Salario")
    market = next(item for item in categories if item["name"] == "Mercado")
    account = e2e_client.post(
        "/api/v1/accounts",
        json={"name": "Banco Principal", "type": "BANK", "opening_balance": "1000000.00"},
        headers=_headers(token, idempotent=True),
    )
    assert account.status_code == 201
    account_id = account.json()["id"]
    common = {"account_id": account_id, "date": date.today().isoformat()}
    income = e2e_client.post(
        "/api/v1/movements",
        json=common | {"type": "INCOME", "category_id": salary["id"], "amount": "2500000.00"},
        headers=_headers(token, idempotent=True),
    )
    expense = e2e_client.post(
        "/api/v1/movements",
        json=common | {"type": "EXPENSE", "category_id": market["id"], "amount": "150000.00"},
        headers=_headers(token, idempotent=True),
    )
    assert income.status_code == expense.status_code == 201

    balance = e2e_client.get("/api/v1/balance", headers=_headers(token))
    assert balance.status_code == 200
    assert balance.json()["consolidated_balance"] == "3350000.00"

    expense_id = expense.json()["movement"]["id"]
    voided = e2e_client.post(f"/api/v1/movements/{expense_id}/void", headers=_headers(token))
    assert voided.status_code == 200
    assert voided.json()["new_balance"] == "3500000.00"
    assert e2e_client.get("/api/v1/balance", headers=_headers(token)).json()["consolidated_balance"] == "3500000.00"
    history = e2e_client.get("/api/v1/movements", headers=_headers(token)).json()["items"]
    original = next(item for item in history if item["id"] == expense_id)
    assert original["status"] == "VOIDED"
    assert any(item["type"] == "VOID" for item in history)
