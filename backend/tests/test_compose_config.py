import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_compose_config() -> dict:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_compose_defines_postgresql_16_database() -> None:
    database = load_compose_config()["services"]["db"]

    assert database["image"] == "postgres:16"
    assert database["environment"] == {
        "POSTGRES_DB": "walletapp",
        "POSTGRES_PASSWORD": "walletapp",
        "POSTGRES_USER": "walletapp",
    }


def test_database_has_healthcheck_and_persistent_volume() -> None:
    database = load_compose_config()["services"]["db"]

    assert "pg_isready" in " ".join(database["healthcheck"]["test"])
    assert any(mount["target"] == "/var/lib/postgresql/data" for mount in database["volumes"])
