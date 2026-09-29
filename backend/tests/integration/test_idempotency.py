from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Journal, JournalLine, JournalResponse


def register_and_login(client: TestClient) -> str:
    assert client.post(
        "/api/v1/auth/register",
        json={"email": "idempotency@example.com", "password": "password-123"},
    ).status_code == 201
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "idempotency@example.com", "password": "password-123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str, key: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(key)}


def movement_setup(client: TestClient, token: str) -> tuple[str, str]:
    categories = client.get(
        "/api/v1/categories",
        params={"type": "INCOME"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "type": "CASH", "opening_balance": "0.00"},
        headers=headers(token, uuid.uuid4()),
    )
    assert account.status_code == 201
    return account.json()["id"], categories[0]["id"]


def test_same_key_persists_one_movement_and_replays_original_response(
    api_client: TestClient,
    committed_session_factory: sessionmaker[Session],
) -> None:
    token = register_and_login(api_client)
    account_id, category_id = movement_setup(api_client, token)
    key = uuid.uuid4()
    payload = {
        "type": "INCOME",
        "account_id": account_id,
        "category_id": category_id,
        "amount": "10.00",
        "date": date.today().isoformat(),
    }

    first = api_client.post("/api/v1/movements", json=payload, headers=headers(token, key))
    second = api_client.post("/api/v1/movements", json=payload, headers=headers(token, key))

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    with committed_session_factory() as session:
        journal_id = uuid.UUID(first.json()["movement"]["id"])
        assert session.scalar(select(func.count()).select_from(Journal).where(Journal.id == journal_id)) == 1
        assert session.scalar(
            select(func.count()).select_from(JournalLine).where(JournalLine.journal_id == journal_id)
        ) == 2
        response = session.get(JournalResponse, (session.scalar(select(Journal.user_id).where(Journal.id == journal_id)), key))
        assert response is not None
        assert response.state == "COMPLETED"


def test_identical_payload_with_different_keys_creates_two_movements(api_client: TestClient) -> None:
    token = register_and_login(api_client)
    account_id, category_id = movement_setup(api_client, token)
    payload = {
        "type": "INCOME",
        "account_id": account_id,
        "category_id": category_id,
        "amount": "10.00",
        "date": date.today().isoformat(),
    }

    first = api_client.post("/api/v1/movements", json=payload, headers=headers(token, uuid.uuid4()))
    second = api_client.post("/api/v1/movements", json=payload, headers=headers(token, uuid.uuid4()))

    assert first.status_code == second.status_code == 201
    assert first.json()["movement"]["id"] != second.json()["movement"]["id"]
    assert second.json()["new_balance"] == "20.00"
