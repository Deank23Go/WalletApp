from __future__ import annotations

import httpx


def test_auth_rotation_reuse_logout_and_rate_limit_over_real_http(e2e_client: httpx.Client) -> None:
    assert e2e_client.get("/api/v1/users/me").status_code == 401
    assert e2e_client.post(
        "/api/v1/auth/register",
        json={"email": "auth-e2e@example.com", "password": "password-123"},
    ).status_code == 201
    login = e2e_client.post(
        "/api/v1/auth/login",
        json={"email": "auth-e2e@example.com", "password": "password-123"},
    )
    assert login.status_code == 200
    old_refresh = login.cookies["refresh_token"]
    access = login.json()["access_token"]
    assert e2e_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access}"},
    ).status_code == 200

    rotated = e2e_client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    assert rotated.cookies["refresh_token"] != old_refresh

    e2e_client.cookies.clear()
    reused = e2e_client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_refresh}"},
    )
    assert reused.status_code == 401
    assert "reutilización" in reused.json()["detail"][0]["message"]

    relogin = e2e_client.post(
        "/api/v1/auth/login",
        json={"email": "auth-e2e@example.com", "password": "password-123"},
    )
    assert relogin.status_code == 200
    assert e2e_client.post("/api/v1/auth/logout").status_code == 204
    assert e2e_client.post("/api/v1/auth/refresh").status_code == 401

    e2e_client.cookies.clear()
    attempts = [
        e2e_client.post(
            "/api/v1/auth/login",
            json={"email": "auth-e2e@example.com", "password": "wrong"},
        )
        for _ in range(9)
    ]
    assert attempts[-1].status_code == 429
