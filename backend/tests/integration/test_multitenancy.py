from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient


def _identity(client: TestClient, email: str) -> str:
    assert client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password-123"},
    ).status_code == 201
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password-123"},
    ).json()["access_token"]


def _auth(token: str, key: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(key)
    return headers


def test_six_cross_tenant_scenarios_do_not_leak_or_mutate_data(api_client: TestClient) -> None:
    owner = _identity(api_client, "owner@example.com")
    outsider = _identity(api_client, "outsider@example.com")
    owner_categories = api_client.get("/api/v1/categories", headers=_auth(owner)).json()
    salary = next(item for item in owner_categories if item["name"] == "Salario")
    custom = api_client.post(
        "/api/v1/categories",
        json={"name": "Private", "type": "INCOME"},
        headers=_auth(owner, uuid.uuid4()),
    ).json()
    account = api_client.post(
        "/api/v1/accounts",
        json={"name": "Private account", "type": "BANK", "opening_balance": "10.00"},
        headers=_auth(owner, uuid.uuid4()),
    ).json()
    movement = api_client.post(
        "/api/v1/movements",
        json={
            "type": "INCOME",
            "account_id": account["id"],
            "category_id": salary["id"],
            "amount": "5.00",
            "date": date.today().isoformat(),
        },
        headers=_auth(owner, uuid.uuid4()),
    ).json()["movement"]

    assert api_client.patch(
        f"/api/v1/accounts/{account['id']}",
        json={"name": "Stolen"},
        headers=_auth(outsider),
    ).status_code == 404
    assert api_client.get("/api/v1/accounts", headers=_auth(outsider)).json() == []
    assert api_client.patch(
        f"/api/v1/categories/{custom['id']}",
        json={"name": "Stolen"},
        headers=_auth(outsider),
    ).status_code == 404
    assert custom["id"] not in {
        item["id"] for item in api_client.get("/api/v1/categories", headers=_auth(outsider)).json()
    }
    filtered = api_client.get(
        "/api/v1/movements",
        params={"account_id": account["id"]},
        headers=_auth(outsider),
    )
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []
    assert api_client.post(
        f"/api/v1/movements/{movement['id']}/void",
        headers=_auth(outsider),
    ).status_code == 404
    assert api_client.get("/api/v1/balance", headers=_auth(outsider)).json() == {
        "consolidated_balance": "0.00",
        "currency": "COP",
        "accounts": [],
    }
