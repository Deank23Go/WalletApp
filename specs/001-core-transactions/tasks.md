# TASKS-001 — Núcleo Transaccional: Desglose de Tareas

**Fuentes**: SPEC-001 (spec.md) y PLAN-001 (plan.md)
**Regla de orden**: migraciones/esquema → modelos y repositorios → dominio/servicios → endpoints/routers → suites de tests. Una fase se considera cerrada solo cuando todos sus checkboxes están marcados y cada verificación "Hecho cuando" pasa.
**Tamaño**: cada tarea es atómica (máx. 20–30 minutos de implementación).

---

## Fase 0 — Arranque del proyecto backend

- [x] **T0.1** Crear esqueleto del paquete backend con dependencias: FastAPI, uvicorn, SQLAlchemy 2, Alembic, pydantic v2, pydantic-settings, argon2-cffi, PyJWT, pytest, pytest-cov, httpx. — Cubre: Plan §5.1.
  - Hecho cuando: `pip install -e .` termina sin errores e `import fastapi` funciona en el entorno del proyecto.
- [x] **T0.2** Crear `app/core/config.py` con pydantic-settings: `DATABASE_URL`, `JWT_SECRET`, `JWT_TTL_SECONDS=900`, límites de rate limit. — Cubre: Plan §1 (core/), §5.7.
  - Hecho cuando: `Settings()` carga variables de entorno y lanza error descriptivo si falta `JWT_SECRET`.
- [x] **T0.3** Crear `docker-compose.yml` con PostgreSQL 16 para desarrollo y tests. — Cubre: Plan §2, §6.2.
  - Hecho cuando: `docker compose up -d db` deja la BD accesible y `pg_isready` responde `accepting connections`.
- [x] **T0.4** Crear `app/main.py` mínimo (composition root) con health check. — Cubre: Plan §1.
  - Hecho cuando: uvicorn arranca y `GET /health` responde 200.
- [x] **T0.5** Inicializar Alembic (`alembic init`, `env.py` conectado a `config.py`). — Cubre: Plan §5.9.
  - Hecho cuando: `alembic current` se ejecuta sin error contra la BD vacía.

## Fase 1 — Esquema y migraciones

- [x] **T1.1** Migración 0001: tipos ENUM (`account_type`, `account_status`, `category_type`, `category_status`, `journal_kind`, `journal_status`, `line_direction`). — Cubre: Plan §2.
  - Hecho cuando: `alembic upgrade head` crea los 7 tipos y `\dT` los lista.
- [x] **T1.2** Migración 0001: tabla `users` con `UNIQUE(email)`, CHECK de formato de email y de moneda. — Cubre: RF-01; Plan §2.
  - Hecho cuando: un INSERT con email duplicado falla con violación de `uq_users_email`.
- [x] **T1.3** Migración 0001: tablas `accounts` y `categories` con FKs, `version` INTEGER en accounts, UNIQUEs y CHECKs de nombre no vacío. — Cubre: RF-02, RF-06; Plan §2.
  - Hecho cuando: un INSERT con nombre en blanco es rechazado por `ck_*_name_not_blank`.
- [x] **T1.4** Migración 0001: tablas `journals` y `journal_lines` con idempotencia única por usuario, `NUMERIC(19,2)`, CHECK de cantidad positiva y exactamente una referencia (cuenta, categoría o externa). — Cubre: RF-03/04/05/09; Plan §2.
  - Hecho cuando: PostgreSQL rechaza líneas con cero o múltiples referencias y acepta la contrapartida externa explícita de un asiento OPENING.
- [x] **T1.5** Migración 0001: tabla `journal_responses` tenant-scoped (`user_id`, `idempotency_key`, estado PENDING/COMPLETED, `status_code`, `body JSONB`, `created_at`). — Cubre: RF-09; Plan §3.
  - Hecho cuando: el mismo usuario no puede reclamar dos veces una clave y dos usuarios distintos sí pueden usar la misma UUID.
- [x] **T1.6** Migración 0001: tabla `refresh_tokens` con `token_hash UNIQUE`, `family_id` y `revoked_at`. — Cubre: RF-01; Plan §2, P5.
  - Hecho cuando: la tabla existe y `\di` muestra `ix_refresh_user`.
- [x] **T1.7** Migración 0001: triggers de inmutabilidad sobre `journals`/`journal_lines` y transición controlada de estado. — Cubre: Plan §2, P1.
  - Hecho cuando: toda mutación o eliminación se rechaza salvo la transición exacta `POSTED → VOIDED` de un journal no VOID.
- [x] **T1.8** Migración 0001: índices (`ix_accounts_user_id`, `ix_categories_user`, `ix_journals_user_date`, `ix_lines_journal/account/category`). — Cubre: Plan §2, RNF-06.
  - Hecho cuando: `\di` muestra los 6 índices definidos en el plan.

## Fase 2 — Modelos y repositorios

- [x] **T2.1** `app/db/session.py`: engine, sessionmaker y factoría de transacciones. — Cubre: Plan §1 (db/session.py).
  - Hecho cuando: begin/commit/rollback funciona contra la BD de Docker en un script de prueba.
- [x] **T2.2** `app/db/models.py`: modelos SQLAlchemy (User, Account, Category, Journal, JournalLine, RefreshToken, JournalResponse) espejo exacto del DDL. — Cubre: Plan §2.
  - Hecho cuando: `alembic check` no detecta diferencias entre modelos y migraciones.
- [x] **T2.3** `app/domain/ports.py`: interfaces UserRepository, AccountRepository, CategoryRepository, JournalRepository, JournalResponseRepository, PasswordHasher, Clock. — Cubre: Plan §1 (ports), P2.
  - Hecho cuando: el análisis de tipos (pyright/mypy) pasa sin errores y ningún puerto importa SQLAlchemy.
- [x] **T2.4** `app/repositories/base.py`: repositorio base con tenant obligatorio y predicado central `user_id`. — Cubre: Plan §1, P5.2.
  - Hecho cuando: los tests cruzados devuelven no encontrado/cero cambios para IDs ajenos y todas las queries financieras usan el predicado central.
- [x] **T2.5** `app/repositories/users_repo.py`: create, get_by_email, get_by_id. — Cubre: RF-01.
  - Hecho cuando: test de repositorio crea un usuario y lo recupera por email e id.
- [x] **T2.6** `app/repositories/accounts_repo.py`: create, list/get/update tenant-scoped, lock de fila, bump_version condicional y balance derivado. — Cubre: RF-02.
  - Hecho cuando: versión correcta devuelve 1, versión obsoleta o cuenta ajena devuelve 0 y el balance ajeno no se expone.
- [x] **T2.7** `app/repositories/categories_repo.py`: CRUD tenant-scoped, filtros type/status y clone_seed_catalog. — Cubre: RF-06, Plan §5.11.
  - Hecho cuando: `clone_seed_catalog()` inserta las categorías con `is_seed=true` solo para el tenant activo.
- [x] **T2.8** `app/repositories/journals_repo.py`: asiento balanceado + 2 líneas, consultas/paginación tenant-scoped, balance, línea de cuenta y anulación atómica. — Cubre: RF-03/04/05/07/08; Plan §3.
  - Hecho cuando: la inserción persiste journal+2 líneas, rechaza referencias ajenas/no balanceadas, balance_query es exacto y void crea el espejo e incrementa version atómicamente.
- [x] **T2.9** `app/repositories/journal_responses_repo.py`: claim atómico, complete y load tenant-scoped. — Cubre: RF-09, Plan §5.10.
  - Hecho cuando: dos conexiones concurrentes producen un solo ganador sin `IntegrityError` y el replay devuelve status/body exactos.

## Fase 3 — Dominio y servicios

- [x] **T3.1** `app/domain/entities.py`: dataclasses User, Account, Category, Journal, JournalLine con montos en `Decimal`. — Cubre: Plan §1 (entities).
  - Hecho cuando: test unitario — construir una JournalLine con `amount=Decimal('150000.00')` conserva el valor exacto.
- [x] **T3.2** `app/domain/seed_catalog.py`: catálogo semilla en español latinoamericano (mín. 4 INCOME, 8 EXPENSE). — Cubre: RF-06, Plan §5.11.
  - Hecho cuando: test — la lista tiene nombres únicos por tipo y todos en español.
- [x] **T3.3** `app/domain/money.py`: helpers de Decimal — cuantización a 2 decimales, validación de >0, suma exacta. — Cubre: RNF-01, CL-09.
  - Hecho cuando: test — `"10.999"` se rechaza, `Decimal('0.1')+Decimal('0.2')==Decimal('0.3')` y `"0"` es rechazado como monto.
- [x] **T3.4** `account_service`: crear cuenta con validaciones (nombre, saldo inicial ≥ 0) y generar asiento OPENING balanceado vía puerto. — Cubre: RF-02, Plan §5.5.
  - Hecho cuando: tests unitarios con repos fake — saldo inicial negativo se rechaza y la apertura crea un journal OPENING con ΣD=ΣC.
- [x] **T3.5** `account_service`: listar con saldo derivado, renombrar, desactivar. — Cubre: RF-02, CA-02.3/02.4/02.5.
  - Hecho cuando: tests unitarios — renombrar no toca journals; desactivar impide nuevos movimientos.
- [x] **T3.6** `category_service`: crear, renombrar, desactivar, reactivar (todas las categorías). — Cubre: RF-06, Plan §5.11.
  - Hecho cuando: tests unitarios cubren CA-06.1 a CA-06.4 con repos fake.
- [x] **T3.7** `movement_service.rules`: validación pura (monto > 0 y 2 decimales, fecha ≤ hoy, categoría por tipo, cuenta activa). — Cubre: RF-03/04/09, CA-03.1..03.4.
  - Hecho cuando: tests unitarios de CL-02, CL-08, CL-09 y categoría inválida pasan sin BD.
- [x] **T3.8** `movement_service.record`: orquestación transaccional del pseudocódigo §3 (lock, verificación de saldo, insert journal+2 líneas, bump version, store response). — Cubre: RF-03/04/09, Plan §3.
  - Hecho cuando: test de integración — movimiento crea 3 filas atómicamente y el saldo derivado refleja el monto exacto.
- [x] **T3.9** `void_service`: anular con espejo de líneas invertidas, estado VOIDED, y `negative_balance_warning`. — Cubre: RF-05, Plan §5.12.
  - Hecho cuando: tests unitarios — el espejo invierte direcciones; anular un journal ya VOIDED falla (CL-04).
- [x] **T3.10** `balance_service`: consolidado sobre cuentas activas + saldos por cuenta derivados. — Cubre: RF-07/08, CA-07.1/07.3/07.4.
  - Hecho cuando: tests unitarios — suma Decimal exacta y exclusión de cuentas INACTIVE.
- [x] **T3.11** `core/security.py`: hash/verify con argon2id. — Cubre: RF-01, P5, Plan §5.8.
  - Hecho cuando: test — `verify(plain, hash(plain))` es True, hash ≠ plaintext y dos hashes del mismo plain difieren.
- [x] **T3.12** `core/security.py`: JWT access (sub/exp/iss) + refresh opaco con hash SHA-256, `family_id` y revocación por reuso. — Cubre: RF-01, P5, Plan §5.7.
  - Hecho cuando: tests unitarios — token expirado falla validación y el reuso de un refresh revoca toda la familia.

## Fase 4 — Endpoints y validación API

- [x] **T4.1** `app/schemas/common.py`: campo Monto (str→Decimal, 2 decimales) y envelope de error `{detail:[{field,message}]}`. — Cubre: RNF-01, CA-09.1.
  - Hecho cuando: test — `"150000.00"` parsea a `Decimal('150000.00')` y `150000.0` (float) es rechazado.
- [x] **T4.2** `app/schemas/`: request/response de auth, accounts, categories, movements y balance. — Cubre: Plan §4.
  - Hecho cuando: test — payload con `amount="abc"` produce error de validación con `field="amount"`.
- [x] **T4.3** `app/api/errors.py`: handlers de excepciones → envelope en español; 500 sin detalles internos. — Cubre: RF-09, RNF-05.
  - Hecho cuando: test — una excepción de dominio produce 422 con `detail[].message` en español.
- [x] **T4.4** `app/api/v1/deps.py`: `current_user` (JWT → usuario), unidad de trabajo, rate limit en auth. — Cubre: RF-01, CA-01.6, P5.
  - Hecho cuando: test — request sin token recibe 401; request con token de un usuario no puede acceder a datos de otro.
- [x] **T4.5** `routers/auth.py`: register, login, refresh, logout, me. — Cubre: RF-01, Plan §4.
  - Hecho cuando: tests de endpoint — CA-01.1 a CA-01.5 verificados vía cliente HTTP (409 correo duplicado, 401 credenciales, cookie refresh, 204 logout).
- [x] **T4.6** `routers/accounts.py`: POST (con Idempotency-Key), GET, PATCH. — Cubre: RF-02, Plan §4.
  - Hecho cuando: tests de endpoint — crear cuenta con apertura devuelve balance correcto; PATCH de una cuenta ajena responde 404.
- [x] **T4.7** `routers/categories.py`: GET (filtro por tipo), POST, PATCH. — Cubre: RF-06, Plan §4.
  - Hecho cuando: tests de endpoint — CA-06.1 a CA-06.4 verificados vía HTTP.
- [x] **T4.8** `routers/movements.py`: POST con header Idempotency-Key, POST void, GET paginado con filtros combinables. — Cubre: RF-03/04/05/08/09, Plan §4.
  - Hecho cuando: tests de endpoint — CL-01, CL-03, CL-04, CL-08 y CL-09 verificados vía HTTP; page_size máximo 100.
- [x] **T4.9** `routers/balance.py`: GET /balance. — Cubre: RF-07, Plan §4.
  - Hecho cuando: test de endpoint — CA-07.1 a CA-07.4 verificados vía HTTP.
- [x] **T4.10** Composición final en `main.py`: routers bajo `/api/v1`, rate limit en auth, `/docs` operativo. — Cubre: Plan §4, P6.
  - Hecho cuando: swagger lista todos los endpoints con rutas kebab-case sin verbos.

## Fase 5 — Suites de tests y gate de CI

- [x] **T5.1** `tests/unit/test_money.py` con fixtures de valores límite (0, -1, 0.001, 10.999, monto máximo). — Cubre: RNF-01, CL-09, Plan §6.1.
  - Hecho cuando: pytest pasa todos los valores límite con el resultado esperado.
- [x] **T5.2** `tests/unit/test_movement_rules.py` — reglas puras de registro. — Cubre: RF-03/04/09, CA-03.1..03.4.
  - Hecho cuando: pytest pasa ≥ 12 casos incluyendo fecha futura y categoría por tipo.
- [x] **T5.3** `tests/unit/test_void_rules.py` — espejo invertido y doble anulación. — Cubre: RF-05, CL-04/11.
  - Hecho cuando: pytest pasa los casos de espejo y de anulación repetida.
- [x] **T5.4** `tests/unit/test_balance_rules.py` — suma exacta, exclusión de inactivas, caso sin cuentas. — Cubre: RF-07, CA-07.1/07.3.
  - Hecho cuando: pytest pasa con los datos fake del plan §6.1.
- [x] **T5.5** `tests/integration/conftest.py` — PostgreSQL en contenedor, truncado entre tests, fixtures usuario/cuenta/categorías. — Cubre: Plan §6.2.
  - Hecho cuando: la suite de integración levanta y limpia la BD automáticamente.
- [x] **T5.6** `tests/integration/test_atomicity.py` — fallo a mitad de transacción. — Cubre: CA-09.3.
  - Hecho cuando: el test que lanza excepción entre inserts verifica 0 filas residuales.
- [x] **T5.7** `tests/integration/test_idempotency.py` — misma clave 1 fila; claves distintas y datos idénticos 2 filas. — Cubre: CL-03, RF-09, hallazgo QA B.2.
  - Hecho cuando: ambos asserts pasan contra PostgreSQL real.
- [x] **T5.8** `tests/integration/test_concurrency.py` — dos egresos simultáneos con saldo para uno solo. — Cubre: P1.4, CL-01, Plan §6.2.
  - Hecho cuando: exactamente un 201 y un 409/422, y el balance final es consistente (sin saldo negativo).
- [x] **T5.9** `tests/integration/test_immutability.py` — triggers contra UPDATE/DELETE. — Cubre: P1, Plan §2.
  - Hecho cuando: los 5 casos de mutación prohibida lanzan excepción y el flip a VOIDED sí pasa.
- [x] **T5.10** `tests/integration/test_derived_balance.py` — apertura + Σ movimientos − Σ anulaciones. — Cubre: P1, Plan §5.5.
  - Hecho cuando: el saldo derivado coincide con la aritmética manual del ejemplo JSON del plan §2.
- [x] **T5.11** `tests/integration/test_multitenancy.py` — accesos cruzados entre usuarios. — Cubre: CA-01.6, RNF-04, P5.2.
  - Hecho cuando: 6 escenarios de acceso cruzado responden 404 o lista vacía.
- [x] **T5.12** `tests/integration/test_deactivation.py` — cuentas y categorías inactivas. — Cubre: CL-05/06, CA-07.1.
  - Hecho cuando: cuenta inactiva rechazada en movimientos nuevos y excluida del consolidado.
- [x] **T5.13** `tests/integration/test_void_flow.py` — flujo completo + saldo negativo con warning. — Cubre: RF-05, Plan §5.12.
  - Hecho cuando: anular un ingreso ya gastado devuelve `negative_balance_warning=true` y saldo negativo exacto.
- [x] **T5.14** `tests/integration/test_seed_catalog.py` — clonado de categorías al registrar. — Cubre: RF-06, Plan §5.11.
  - Hecho cuando: un usuario nuevo recibe exactamente las N categorías seed con `is_seed=true`.
- [x] **T5.15** `tests/e2e/test_happy_path.py` — viaje completo del plan §6.3. — Cubre: RF-01..05, RF-07.
  - Hecho cuando: balance final es "3350000.00" y tras anular el egreso es "3500000.00".
- [x] **T5.16** `tests/e2e/test_error_envelope.py` — envelopes 422 en español. — Cubre: CA-09.1, RNF-05.
  - Hecho cuando: cada caso 422 devuelve `detail` con `field` y `message` en español latinoamericano.
- [x] **T5.17** `tests/e2e/test_auth_flow.py` — 401 sin token, 429 rate limit, rotación y reuso de refresh. — Cubre: RF-01, P5.
  - Hecho cuando: el reuso de un refresh rotado devuelve 401 y revoca la familia.
- [x] **T5.18** Cobertura: pytest-cov con umbral ≥ 90% en `domain/` y flujos transaccionales de `api/`. — Cubre: P4.
  - Hecho cuando: `pytest --cov --cov-fail-under=90` falla si la cobertura baja del umbral.
- [x] **T5.19** CI: pipeline con lint + tests + cobertura que bloquea el merge ante fallo. — Cubre: P4.
  - Hecho cuando: verificado que un commit con un test roto produce pipeline en rojo.

---

## Trazabilidad rápida: fase → RF

| Fase | RF / RNF / Principios |
|---|---|
| 0 — Arranque | Plan §1, §5 |
| 1 — Esquema y migraciones | RF-01, RF-02, RF-03/04/05/09, RF-06; P1, P5 |
| 2 — Modelos y repositorios | RF-01, RF-02, RF-03/04/05/07/08, RF-06, RF-09; P2, P5 |
| 3 — Dominio y servicios | RF-01, RF-02, RF-03/04/09, RF-05, RF-06, RF-07/08; RNF-01 |
| 4 — Endpoints API | RF-01..RF-09; RNF-05, P5, P6 |
| 5 — Tests y CI | RF-01..RF-09; CL-01..CL-11; RNF-01..07; P4 |
