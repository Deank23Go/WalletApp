import ast
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[2] / "app" / "domain"
FORBIDDEN_PREFIXES = (
    "alembic",
    "fastapi",
    "sqlalchemy",
    "starlette",
    "app.api",
    "app.db",
    "app.repositories",
)


def test_domain_does_not_import_infrastructure() -> None:
    violations: list[str] = []
    for path in DOMAIN_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path.relative_to(DOMAIN_ROOT)} imports {module}")
    assert violations == []
