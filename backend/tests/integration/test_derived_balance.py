from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Account
from app.repositories.accounts_repo import SqlAccountRepository


def _register_and_login(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": "derived@example.com", "password": "password-123"},
    )
    return client.post(
        "/api/v1/auth/login",
        json={"email": "derived@example.com", "password": "password-123"},
    ).json()["access_token"]


def _headers(token: str, *, key: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(key)
    return headers


def test_balance_is_derived_from_opening_movements_and_voids(
    api_client: TestClient,
    committed_session_factory: sessionmaker[Session],
) -> None:
    token = _register_and_login(api_client)
    categories = api_client.get("/api/v1/categories", headers=_headers(token)).json()
    salary = next(item for item in categories if item["name"] == "Salario")
    market = next(item for item in categories if item["name"] == "Mercado")
    account = api_client.post(
        "/api/v1/accounts",
        json={"name": "Bank", "type": "BANK", "opening_balance": "1000000.00"},
        headers=_headers(token, key=uuid.uuid4()),
    ).json()
    account_id = account["id"]
    payload = {
        "account_id": account_id,
        "date": date.today().isoformat(),
        "note": None,
    }
    income = api_client.post(
        "/api/v1/movements",
        json=payload | {"type": "INCOME", "category_id": salary["id"], "amount": "2500000.00"},
        headers=_headers(token, key=uuid.uuid4()),
    )
    expense = api_client.post(
        "/api/v1/movements",
        json=payload | {"type": "EXPENSE", "category_id": market["id"], "amount": "150000.00"},
        headers=_headers(token, key=uuid.uuid4()),
    )

    assert income.status_code == expense.status_code == 201
    assert api_client.get("/api/v1/balance", headers=_headers(token)).json()["consolidated_balance"] == "3350000.00"
    voided = api_client.post(
        f"/api/v1/movements/{expense.json()['movement']['id']}/void",
        headers=_headers(token),
    )
    assert voided.status_code == 200
    assert voided.json()["new_balance"] == "3500000.00"

    with committed_session_factory() as session:
        account_uuid = uuid.UUID(account_id)
        account_record = session.get(Account, account_uuid)
        assert account_record is not None
        assert SqlAccountRepository(session, account_record.user_id).get_balance(account_uuid) == Decimal("3500000.00")
