from __future__ import annotations

import uuid
from datetime import date, timedelta

import httpx


def _session(client: httpx.Client) -> tuple[str, str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": "errors@example.com", "password": "password-123"},
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "errors@example.com", "password": "password-123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    categories = client.get("/api/v1/categories", headers=headers).json()
    salary = next(item for item in categories if item["name"] == "Salario")
    market = next(item for item in categories if item["name"] == "Mercado")
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "type": "CASH", "opening_balance": "10.00"},
        headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
    ).json()
    return token, account["id"], salary["id"] + ":" + market["id"]


def assert_error_envelope(response: httpx.Response, expected_field: str) -> None:
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body.get("detail"), list)
    assert body["detail"][0]["field"] == expected_field
    assert body["detail"][0]["message"]
    serialized = response.text.lower()
    assert "traceback" not in serialized
    assert "sqlalchemy" not in serialized


def test_unauthenticated_and_validation_errors_use_spanish_envelope(e2e_client: httpx.Client) -> None:
    unauthorized = e2e_client.get("/api/v1/balance")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"][0]["message"] == "Debe iniciar sesión para continuar"
    token, account_id, categories = _session(e2e_client)
    salary_id, market_id = categories.split(":")
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}
    common = {
        "type": "INCOME",
        "account_id": account_id,
        "category_id": salary_id,
        "date": date.today().isoformat(),
    }

    for amount in ("0", "1.001", 1.0):
        response = e2e_client.post(
            "/api/v1/movements",
            json=common | {"amount": amount},
            headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
        )
        assert_error_envelope(response, "amount")

    future = e2e_client.post(
        "/api/v1/movements",
        json=common | {"amount": "1.00", "date": (date.today() + timedelta(days=1)).isoformat()},
        headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert_error_envelope(future, "date")
    wrong_category = e2e_client.post(
        "/api/v1/movements",
        json=common | {"amount": "1.00", "category_id": market_id},
        headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert_error_envelope(wrong_category, "category_id")
