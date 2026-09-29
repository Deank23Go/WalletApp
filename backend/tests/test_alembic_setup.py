from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_configuration_has_migration_directory() -> None:
    config = Config(BACKEND_ROOT / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    assert Path(scripts.dir).resolve() == (BACKEND_ROOT / "alembic").resolve()
    assert (BACKEND_ROOT / "alembic" / "versions").is_dir()


def test_alembic_environment_uses_application_settings() -> None:
    environment = (BACKEND_ROOT / "alembic" / "env.py").read_text()

    assert "Settings" in environment
    assert "settings.database_url" in environment
    assert "driver://user:pass" not in environment
