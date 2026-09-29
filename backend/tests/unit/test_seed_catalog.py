from app.domain.seed_catalog import SEED_CATALOG


def test_seed_catalog_has_unique_spanish_categories_by_type() -> None:
    income = [item["name"] for item in SEED_CATALOG if item["type"] == "INCOME"]
    expense = [item["name"] for item in SEED_CATALOG if item["type"] == "EXPENSE"]

    assert len(income) >= 4
    assert len(expense) >= 8
    assert len({(item["type"], item["name"].casefold()) for item in SEED_CATALOG}) == len(SEED_CATALOG)
    assert {item["type"] for item in SEED_CATALOG} == {"INCOME", "EXPENSE"}
    assert {"Salario", "Mercado", "Transporte", "Salud"} <= {item["name"] for item in SEED_CATALOG}
