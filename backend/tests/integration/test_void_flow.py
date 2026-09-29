from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Journal, JournalLine


def _headers(token: str, key: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(key)
    return headers


def test_voiding_spent_income_returns_exact_negative_balance_and_warning(
    api_client: TestClient,
    committed_session_factory: sessionmaker[Session],
) -> None:
    api_client.post(
        "/api/v1/auth/register",
        json={"email": "negative-void@example.com", "password": "password-123"},
    )
    token = api_client.post(
        "/api/v1/auth/login",
        json={"email": "negative-void@example.com", "password": "password-123"},
    ).json()["access_token"]
    categories = api_client.get("/api/v1/categories", headers=_headers(token)).json()
    salary = next(item for item in categories if item["name"] == "Salario")
    market = next(item for item in categories if item["name"] == "Mercado")
    account = api_client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "type": "CASH", "opening_balance": "100.00"},
        headers=_headers(token, uuid.uuid4()),
    ).json()
    common = {"account_id": account["id"], "date": date.today().isoformat()}
    income = api_client.post(
        "/api/v1/movements",
        json=common | {"type": "INCOME", "category_id": salary["id"], "amount": "50.00"},
        headers=_headers(token, uuid.uuid4()),
    ).json()
    expense = api_client.post(
        "/api/v1/movements",
        json=common | {"type": "EXPENSE", "category_id": market["id"], "amount": "120.00"},
        headers=_headers(token, uuid.uuid4()),
    )
    assert expense.status_code == 201
    movement_id = uuid.UUID(income["movement"]["id"])

    voided = api_client.post(f"/api/v1/movements/{movement_id}/void", headers=_headers(token))

    assert voided.status_code == 200
    assert voided.json()["new_balance"] == "-20.00"
    assert voided.json()["negative_balance_warning"] is True
    with committed_session_factory() as session:
        original = session.get(Journal, movement_id)
        assert original is not None
        assert original.status == "VOIDED"
        void_entry = session.scalar(select(Journal).where(Journal.voided_journal_id == movement_id))
        assert void_entry is not None
        assert session.scalar(
            select(func.count()).select_from(JournalLine).where(JournalLine.journal_id == void_entry.id)
        ) == 2

    repeated = api_client.post(f"/api/v1/movements/{movement_id}/void", headers=_headers(token))
    assert repeated.status_code == 422
    with committed_session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(Journal).where(Journal.voided_journal_id == movement_id)
        ) == 1
