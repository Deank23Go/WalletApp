from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient


def _headers(token: str, key: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(key)
    return headers


def test_inactive_category_rejects_new_movements_but_preserves_history(api_client: TestClient) -> None:
    api_client.post(
        "/api/v1/auth/register",
        json={"email": "deactivation@example.com", "password": "password-123"},
    )
    token = api_client.post(
        "/api/v1/auth/login",
        json={"email": "deactivation@example.com", "password": "password-123"},
    ).json()["access_token"]
    categories = api_client.get("/api/v1/categories", headers=_headers(token)).json()
    market = next(item for item in categories if item["name"] == "Mercado")
    account = api_client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "type": "CASH", "opening_balance": "20.00"},
        headers=_headers(token, uuid.uuid4()),
    ).json()
    payload = {
        "type": "EXPENSE",
        "account_id": account["id"],
        "category_id": market["id"],
        "amount": "5.00",
        "date": date.today().isoformat(),
    }
    posted = api_client.post(
        "/api/v1/movements",
        json=payload,
        headers=_headers(token, uuid.uuid4()),
    )
    assert posted.status_code == 201
    assert api_client.patch(
        f"/api/v1/categories/{market['id']}",
        json={"status": "INACTIVE"},
        headers=_headers(token),
    ).status_code == 200

    rejected = api_client.post(
        "/api/v1/movements",
        json=payload,
        headers=_headers(token, uuid.uuid4()),
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"][0]["field"] == "category_id"
    history = api_client.get("/api/v1/movements", headers=_headers(token)).json()["items"]
    historical = next(item for item in history if item["id"] == posted.json()["movement"]["id"])
    assert historical["category"] == {"id": market["id"], "name": "Mercado"}

    assert api_client.patch(
        f"/api/v1/accounts/{account['id']}",
        json={"status": "INACTIVE"},
        headers=_headers(token),
    ).status_code == 200
    assert api_client.get("/api/v1/balance", headers=_headers(token)).json()["consolidated_balance"] == "0.00"
