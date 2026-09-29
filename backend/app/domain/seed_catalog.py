"""
app/domain/seed_catalog.py
Seed category catalog in Latin American Spanish.
Cloned for each new user at registration (is_seed=True).
Covers T3.2 — RF-06, Plan §5.11.
Minimum: 4 INCOME + 8 EXPENSE categories.
"""
from __future__ import annotations

SEED_CATALOG: list[dict[str, str]] = [
    # -----------------------------------------------------------------------
    # INCOME — at least 4
    # -----------------------------------------------------------------------
    {"name": "Salario",             "type": "INCOME"},
    {"name": "Freelance",           "type": "INCOME"},
    {"name": "Arriendos",           "type": "INCOME"},
    {"name": "Inversiones",         "type": "INCOME"},
    {"name": "Bonificaciones",      "type": "INCOME"},
    {"name": "Otros ingresos",      "type": "INCOME"},
    # -----------------------------------------------------------------------
    # EXPENSE — at least 8
    # -----------------------------------------------------------------------
    {"name": "Mercado",             "type": "EXPENSE"},
    {"name": "Restaurantes",        "type": "EXPENSE"},
    {"name": "Transporte",          "type": "EXPENSE"},
    {"name": "Arriendo",            "type": "EXPENSE"},
    {"name": "Servicios públicos",  "type": "EXPENSE"},
    {"name": "Salud",               "type": "EXPENSE"},
    {"name": "Educación",           "type": "EXPENSE"},
    {"name": "Entretenimiento",     "type": "EXPENSE"},
    {"name": "Ropa y calzado",      "type": "EXPENSE"},
    {"name": "Tecnología",          "type": "EXPENSE"},
    {"name": "Viajes",              "type": "EXPENSE"},
    {"name": "Otros gastos",        "type": "EXPENSE"},
]
