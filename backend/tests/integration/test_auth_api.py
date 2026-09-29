from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Category, RefreshToken, User
from app.domain.seed_catalog import SEED_CATALOG


def register(client: TestClient, email: str = "ana@example.com"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": "password-123"})


def login(client: TestClient, email: str = "ana@example.com", password: str = "password-123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_auth_registration_login_me_refresh_reuse_and_logout(
    api_client: TestClient,
    committed_session_factory: sessionmaker[Session],
) -> None:
    registration = register(api_client, "ANA@EXAMPLE.COM")
    assert registration.status_code == 201
    assert registration.json()["email"] == "ana@example.com"
    assert register(api_client).status_code == 409

    with committed_session_factory() as session:
        user_id = session.scalar(select(User.id).where(User.email == "ana@example.com"))
        seeded = list(session.scalars(select(Category).where(Category.user_id == user_id)))
        assert len(seeded) == len(SEED_CATALOG)
        assert all(category.is_seed and category.user_id == user_id for category in seeded)
        assert {(category.name, category.type) for category in seeded} == {
            (item["name"], item["type"]) for item in SEED_CATALOG
        }

    assert login(api_client, password="incorrect").status_code == 401
    session_response = login(api_client)
    assert session_response.status_code == 200
    assert session_response.json()["token_type"] == "bearer"
    old_refresh = session_response.cookies["refresh_token"]
    cookie_header = session_response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "secure" in cookie_header
    assert "samesite=strict" in cookie_header

    access_token = session_response.json()["access_token"]
    me = api_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ana@example.com"
    assert api_client.get("/api/v1/users/me").status_code == 401

    rotated = api_client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    assert rotated.cookies["refresh_token"] != old_refresh

    api_client.cookies.clear()
    reused = api_client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_refresh}"},
    )
    assert reused.status_code == 401
    assert "reutilización" in reused.json()["detail"][0]["message"]
    with committed_session_factory() as session:
        assert all(token.revoked_at is not None for token in session.scalars(select(RefreshToken)).all())

    latest_login = login(api_client)
    assert latest_login.status_code == 200
    logout = api_client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert api_client.post("/api/v1/auth/refresh").status_code == 401


def test_login_rate_limit_returns_uniform_429(api_client: TestClient) -> None:
    register(api_client)

    responses = [login(api_client, password="wrong") for _ in range(11)]

    assert [response.status_code for response in responses[:10]] == [401] * 10
    assert responses[10].status_code == 429
    assert responses[10].json() == {
        "detail": [
            {
                "field": "general",
                "message": "Se alcanzó el límite de intentos. Intente nuevamente más tarde",
            }
        ]
    }
