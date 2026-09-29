# PLAN-001 — Núcleo Transaccional: Plan Técnico

**Spec vinculado**: SPEC-001 (specs/001-core-transactions/spec.md)
**Constitución**: docs/constitution.md (fuente autoritativa; prevalece sobre cualquier supuesto del spec)
**Versión**: 1.0
**Estado**: Borrador
**Fecha**: 2026-09-21

---

## 1. Estructura de módulos y capas

Organización backend bajo arquitectura limpia (P2 de la constitución): **API → Dominio → Persistencia**, con dependencias solo hacia adentro. El dominio no importa frameworks, ORM ni HTTP. El frontend queda fuera de este plan (plan técnico separado).

```
WalletApp/
├── backend/
│   ├── alembic/                      # migraciones versionadas
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                   # composition root: wiring de dependencias
│   │   ├── api/                      # CAPA API — HTTP, auth, serialización
│   │   │   ├── v1/
│   │   │   │   ├── routers/
│   │   │   │   │   ├── auth.py        # RF-01
│   │   │   │   │   ├── accounts.py    # RF-02
│   │   │   │   │   ├── categories.py  # RF-06
│   │   │   │   │   ├── movements.py   # RF-03, RF-04, RF-05, RF-09
│   │   │   │   │   └── balance.py     # RF-07, RF-08
│   │   │   │   └── deps.py            # current_user (tenant), uow, rate limit
│   │   │   └── errors.py              # excepción → {detail:[{field,message}]} en español
│   │   ├── schemas/                   # Pydantic v2: request/response (monto como str→Decimal)
│   │   │   ├── auth.py  accounts.py  categories.py  movements.py  common.py
│   │   ├── domain/                    # CAPA DOMINIO — reglas financieras puras (sin ORM/HTTP)
│   │   │   ├── entities.py            # User, Account, Category, Journal, JournalLine
│   │   │   ├── ports.py               # interfaces (repos, hasher, clock) — dominio define
│   │   │   └── services/
│   │   │       ├── account_service.py   # RF-02
│   │   │       ├── category_service.py  # RF-06
│   │   │       ├── movement_service.py  # RF-03/04/09: validación, saldo, asiento
│   │   │       ├── void_service.py      # RF-05: anulación con contramovimiento
│   │   │       └── balance_service.py   # RF-07/08: saldos derivados, consolidado
│   │   ├── repositories/              # CAPA PERSISTENCIA — implementan ports con SQLAlchemy
│   │   │   ├── users_repo.py  accounts_repo.py  categories_repo.py  journals_repo.py
│   │   │   └── base.py                # filtro user_id impuesto centralmente (P5 multitenancy)
│   │   ├── db/
│   │   │   ├── models.py              # modelos ORM (solo definición de esquema)
│   │   │   ├── session.py             # engine, sessionmaker, unit of work
│   │   │   └── immutability_triggers.sql
│   │   └── core/
│   │       ├── config.py              # settings (pydantic-settings)
│   │       ├── security.py            # argon2id, JWT access, refresh rotativo
│   │       └── idempotency.py         # almacén de respuestas por Idempotency-Key
│   └── tests/
│       ├── unit/                      # dominio puro
│       ├── integration/               # PostgreSQL real (contenedor)
│       └── e2e/                       # API completa
```

**Regla de dependencias**: `api → domain ← repositories`; `repositories` implementa `domain/ports.py`. Un caso de uso financiero debe poder ejecutarse sin servidor web ni base de datos (verificación de P2).

**Cobertura RF**: RF-01..RF-09 distribuidos como se anota en cada módulo; tabla de trazabilidad al final del documento.

---

## 2. Modelo de datos relacional

PostgreSQL 16. Montos en `NUMERIC(19,2)` (nunca float — P1/RNF-01). Partida doble explícita: cada movimiento es un **asiento** (`journals`) con exactamente dos **líneas** (`journal_lines`) balanceadas. El saldo de cuenta **no se almacena**: se deriva de las líneas (P1 "saldo derivable de sus asientos"). El saldo inicial se registra como asiento `OPENING` — la constitución prevalece sobre el supuesto DA-01 del spec.

```sql
-- Types
CREATE TYPE account_type    AS ENUM ('CASH', 'BANK');
CREATE TYPE account_status  AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE category_type   AS ENUM ('INCOME', 'EXPENSE');
CREATE TYPE category_status AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE journal_kind    AS ENUM ('OPENING', 'INCOME', 'EXPENSE', 'VOID');
CREATE TYPE journal_status  AS ENUM ('POSTED', 'VOIDED');
CREATE TYPE line_direction  AS ENUM ('DEBIT', 'CREDIT');

CREATE TABLE users (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email              VARCHAR(254) NOT NULL,
  password_hash      TEXT NOT NULL,                 -- argon2id, never stored in logs
  preferred_currency CHAR(3) NOT NULL DEFAULT 'COP',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_users_email UNIQUE (email),
  CONSTRAINT ck_users_email_format CHECK (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  CONSTRAINT ck_users_currency CHECK (preferred_currency ~ '^[A-Z]{3}$')
);
-- email normalized to lowercase at the API boundary (CA-01.1)

CREATE TABLE accounts (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  name       VARCHAR(60) NOT NULL,
  type       account_type NOT NULL,
  status     account_status NOT NULL DEFAULT 'ACTIVE',
  version    INTEGER NOT NULL DEFAULT 1,           -- optimistic locking (P1.4)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_accounts_user_name UNIQUE (user_id, name),
  CONSTRAINT ck_accounts_name_not_blank CHECK (btrim(name) <> '')
);
CREATE INDEX ix_accounts_user_id ON accounts (user_id);

CREATE TABLE categories (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name       VARCHAR(60) NOT NULL,
  type       category_type NOT NULL,
  is_seed    BOOLEAN NOT NULL DEFAULT FALSE,       -- cloned from seed catalog at registration
  status     category_status NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_categories_user_name_type UNIQUE (user_id, name, type),
  CONSTRAINT ck_categories_name_not_blank CHECK (btrim(name) <> '')
);
CREATE INDEX ix_categories_user ON categories (user_id, type, status);

CREATE TABLE journals (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  kind              journal_kind NOT NULL,
  status            journal_status NOT NULL DEFAULT 'POSTED',
  date              DATE NOT NULL,                 -- accounting date; future dates rejected at API
  note              VARCHAR(255),
  idempotency_key   UUID NOT NULL,                 -- header Idempotency-Key (CA-09.2/CL-03)
  voided_journal_id UUID REFERENCES journals(id) ON DELETE RESTRICT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_journals_idempotency UNIQUE (idempotency_key),
  CONSTRAINT ck_journals_void_link CHECK (
    (kind = 'VOID' AND voided_journal_id IS NOT NULL) OR
    (kind <> 'VOID' AND voided_journal_id IS NULL)
  )
);
CREATE INDEX ix_journals_user_date ON journals (user_id, date DESC, created_at DESC);

CREATE TABLE journal_lines (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journal_id  UUID NOT NULL REFERENCES journals(id) ON DELETE RESTRICT,
  account_id  UUID REFERENCES accounts(id) ON DELETE RESTRICT,
  category_id UUID REFERENCES categories(id) ON DELETE RESTRICT,
  direction   line_direction NOT NULL,
  amount      NUMERIC(19,2) NOT NULL,
  CONSTRAINT ck_lines_amount_positive CHECK (amount > 0),
  CONSTRAINT ck_lines_exactly_one_account CHECK (
    (account_id IS NOT NULL AND category_id IS NULL) OR  -- line of the affected account
    (account_id IS NULL)                                 -- counterparty line (category or external)
  )
);
CREATE INDEX ix_lines_journal  ON journal_lines (journal_id);
CREATE INDEX ix_lines_account  ON journal_lines (account_id);
CREATE INDEX ix_lines_category ON journal_lines (category_id);

-- Balance is DERIVED, never stored (P1):
--   balance(account) = SUM(debit lines) - SUM(credit lines) of that account
--   SELECT COALESCE(SUM(CASE WHEN direction = 'DEBIT' THEN amount ELSE -amount END), 0)
--     FROM journal_lines WHERE account_id = :account_id;

-- Immutability (P1): only the VOIDED status flip is allowed on journals.
CREATE FUNCTION forbid_journal_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'journal entries are immutable';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_journals_no_update
  BEFORE UPDATE OF date, note, kind, idempotency_key, voided_journal_id
  ON journals FOR EACH ROW EXECUTE FUNCTION forbid_journal_mutation();
CREATE TRIGGER trg_journals_no_delete
  BEFORE DELETE ON journals FOR EACH ROW EXECUTE FUNCTION forbid_journal_mutation();
CREATE TRIGGER trg_lines_no_update
  BEFORE UPDATE ON journal_lines FOR EACH ROW EXECUTE FUNCTION forbid_journal_mutation();
CREATE TRIGGER trg_lines_no_delete
  BEFORE DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION forbid_journal_mutation();

-- Rotating refresh tokens (P5): only SHA-256 hashes stored, family for reuse detection
CREATE TABLE refresh_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  family_id  UUID NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_user ON refresh_tokens (user_id);
```

### Ejemplo de carga de datos (JSON)

Escenario: Ana abre su cuenta bancaria con $1.000.000, recibe salario de $2.500.000 y gasta $150.000 en mercado. Balance final derivado: 1.000.000 + 2.500.000 − 150.000 = **3.350.000,00**.

```json
{
  "user": { "id": "7f2b4c9e-0000-0000-0000-000000000001", "email": "ana@example.com", "preferred_currency": "COP" },
  "accounts": [
    { "id": "a1000000-0000-0000-0000-000000000001", "name": "Banco Principal", "type": "BANK", "status": "ACTIVE", "version": 4 }
  ],
  "categories": [
    { "id": "c1000000-0000-0000-0000-000000000001", "name": "Salario", "type": "INCOME",  "is_seed": true,  "status": "ACTIVE" },
    { "id": "c2000000-0000-0000-0000-000000000002", "name": "Mercado", "type": "EXPENSE", "is_seed": true,  "status": "ACTIVE" }
  ],
  "journals": [
    {
      "id": "j1000000-0000-0000-0000-000000000001", "kind": "OPENING", "status": "POSTED", "date": "2026-09-01",
      "lines": [
        { "account": "a1000000-0000-0000-0000-000000000001", "category": null, "direction": "DEBIT",  "amount": "1000000.00" },
        { "account": null, "category": null, "direction": "CREDIT", "amount": "1000000.00" }
      ]
    },
    {
      "id": "j1000000-0000-0000-0000-000000000002", "kind": "INCOME", "status": "POSTED", "date": "2026-09-15",
      "lines": [
        { "account": "a1000000-0000-0000-0000-000000000001", "category": null, "direction": "DEBIT",  "amount": "2500000.00" },
        { "account": null, "category": "c1000000-0000-0000-0000-000000000001", "direction": "CREDIT", "amount": "2500000.00" }
      ]
    },
    {
      "id": "j1000000-0000-0000-0000-000000000003", "kind": "EXPENSE", "status": "POSTED", "date": "2026-09-16",
      "lines": [
        { "account": "a1000000-0000-0000-0000-000000000001", "category": null, "direction": "CREDIT", "amount": "150000.00" },
        { "account": null, "category": "c2000000-0000-0000-0000-000000000002", "direction": "DEBIT",  "amount": "150000.00" }
      ]
    }
  ]
}
```

**Invariantes verificables (P1)**: cada asiento tiene 2 líneas; Σ DEBIT = Σ CREDIT; el saldo derivado de la cuenta coincide con la aritmética manual del ejemplo.

**Cobertura RF**: RF-02 (accounts, apertura), RF-03/04 (INCOME/EXPENSE con contrapartida), RF-05 (kind VOID), RF-06 (categories con seed), RF-09/CA-09.2 (uq_journals_idempotency), RNF-04 (user_id en todas las tablas), P5 (refresh_tokens).

---

## 3. Lógica de negocio crítica (pseudocódigo)

Narrativa: los dos algoritmos transaccionales deben ser **atómicos** (todo o nada — CA-09.3) y **a prueba de carreras** (CL-01 no puede violarse por escrituras simultáneas). Estrategia: `SELECT ... FOR UPDATE` sobre la fila de cuenta para serializar la verificación de saldo, más `UPDATE ... WHERE version = :expected` (bloqueo optimista, P1.4) como contrato de detección de conflictos. Ver sección 5, decisión 6.

```
# record_movement — registers an INCOME or EXPENSE journal atomically.
# Covers RF-03, RF-04, RF-09. Edge cases CL-01, CL-02, CL-03, CL-08, CL-09.
procedure record_movement(user, request):
    # request already validated at the API boundary (Pydantic):
    #   amount: Decimal > 0, quantized to 2 decimals (CL-09)
    #   date <= today (CA-03.4, CL-08)
    #   note: <= 255 chars; type in {INCOME, EXPENSE}
    tx = db.begin_transaction(isolation=READ_COMMITTED)
    try:
        account = tx.execute("""
            SELECT id, user_id, type, status, version
            FROM accounts
            WHERE id = :account_id AND user_id = :user_id
            FOR UPDATE""")                       # row lock serializes writers of this account
        if account is None:
            tx.rollback(); return 404 "La cuenta no existe"
        if account.status != ACTIVE:
            tx.rollback(); return 422 "La cuenta está inactiva"        # CA-03.2

        category = tx.execute("""
            SELECT id, type, status FROM categories
            WHERE id = :category_id AND user_id = :user_id""")
        if category is None or category.status != ACTIVE or category.type != request.type:
            tx.rollback(); return 422 "La categoría no es válida para este tipo de movimiento"  # CA-03.3

        replay = tx.execute("""
            SELECT stored_response FROM journal_responses
            WHERE idempotency_key = :key""")
        if replay is not None:
            tx.rollback(); return 200 with replay.stored_response   # CL-03: replay returns original result

        balance = tx.execute("""
            SELECT COALESCE(SUM(CASE WHEN direction = 'DEBIT'
                                     THEN amount ELSE -amount END), 0)
            FROM journal_lines WHERE account_id = :account_id""")    # derived balance (P1)

        if request.type == EXPENSE and request.amount > balance:
            tx.rollback(); return 422 {
                field: "amount",
                message: "Saldo insuficiente en la cuenta",          # CA-04.2 / CL-01
                available_balance: balance
            }

        journal = tx.insert("journals", {
            kind: request.type, status: POSTED, date: request.date,
            note: request.note, idempotency_key: request.idempotency_key,
            user_id: user.id, voided_journal_id: NULL
        })
        if request.type == INCOME:                                   # debit the account
            tx.insert("journal_lines", {journal_id, account_id: account.id,
                        category_id: NULL, direction: DEBIT, amount: request.amount})
            tx.insert("journal_lines", {journal_id, account_id: NULL,
                        category_id: category.id, direction: CREDIT, amount: request.amount})
        else:                                                        # EXPENSE: credit the account
            tx.insert("journal_lines", {journal_id, account_id: account.id,
                        category_id: NULL, direction: CREDIT, amount: request.amount})
            tx.insert("journal_lines", {journal_id, account_id: NULL,
                        category_id: category.id, direction: DEBIT, amount: request.amount})
        # Invariant P1: exactly 2 lines, SUM(DEBIT) = SUM(CREDIT) — enforced by code + tests

        updated = tx.execute("""
            UPDATE accounts
            SET version = version + 1, updated_at = now()
            WHERE id = :account_id AND version = :expected_version""",   # optimistic lock (P1.4)
            expected_version = account.version)
        if updated.rowcount == 0:
            tx.rollback(); return 409 "Conflicto de concurrencia, reintente la operación"

        tx.store_response(idempotency_key, 201_response)              # before commit, for replays
        tx.commit()
        return 201 {movement, new_balance: balance ± request.amount}  # exact Decimal math (RNF-01)
    except:
        tx.rollback()                                                 # CA-09.3: no partial writes
        return 500 (generic, no internal details)
```

```
# void_movement — annuls a confirmed movement with an automatic reverse journal.
# Covers RF-05. Edge cases CL-04, CL-11, and the QA finding B.4 (void may leave a
# negative balance: corrections are always allowed; a warning is returned).
procedure void_movement(user, movement_id):
    tx = db.begin_transaction(isolation=READ_COMMITTED)
    try:
        original = tx.execute("""
            SELECT * FROM journals
            WHERE id = :movement_id AND user_id = :user_id AND kind <> 'VOID'
            FOR UPDATE""")
        if original is None:
            tx.rollback(); return 404 "El movimiento no existe"
        if original.status == VOIDED:
            tx.rollback(); return 422 "El movimiento ya está anulado"   # CA-05.3 / CL-04

        account = tx.execute("""
            SELECT * FROM accounts
            WHERE id = :account_id FOR UPDATE""", account_id = original.account_id)

        void_journal = tx.insert("journals", {
            kind: VOID, status: POSTED, date: today,
            note: NULL, idempotency_key: new_uuid(),
            voided_journal_id: original.id, user_id: user.id
        })
        for line in original.lines:                                   # mirror, inverted directions
            tx.insert("journal_lines", {
                journal_id: void_journal.id,
                account_id: line.account_id, category_id: line.category_id,
                direction: opposite(line.direction), amount: line.amount
            })

        tx.execute("UPDATE journals SET status = 'VOIDED' WHERE id = :id", id = original.id)
        # Only mutation the immutability trigger permits (see section 2)

        updated = tx.execute("""
            UPDATE accounts SET version = version + 1, updated_at = now()
            WHERE id = :account_id AND version = :expected_version""", expected_version = account.version)
        if updated.rowcount == 0:
            tx.rollback(); return 409 "Conflicto de concurrencia, reintente la operación"

        new_balance = derived_balance(account.id)                     # CA-05.2: exact restoration
        tx.commit()
        return 200 {
            void_movement: void_journal,
            new_balance: new_balance,
            negative_balance_warning: new_balance < 0                 # decision 12 (section 5)
        }
    except:
        tx.rollback(); return 500
```

```
# consolidated_balance — derived consolidated balance over ACTIVE accounts only.
# Covers RF-07 (CA-07.1, CA-07.3, CA-07.4) and RF-08 filtering aggregation.
procedure consolidated_balance(user):
    rows = db.execute("""
        SELECT a.id, a.name, a.type,
               COALESCE(SUM(CASE WHEN l.direction = 'DEBIT'
                                 THEN l.amount ELSE -l.amount END), 0) AS balance
        FROM accounts a
        LEFT JOIN journal_lines l ON l.account_id = a.id
        WHERE a.user_id = :user_id AND a.status = 'ACTIVE'
        GROUP BY a.id, a.name, a.type
        ORDER BY a.created_at ASC""")
    total = sum(row.balance for row in rows)                          # exact Decimal sum (RNF-01)
    return {consolidated_balance: total, currency: user.preferred_currency, accounts: rows}
```

**Cobertura RF**: RF-03/04/09 (registro atómico, rechazos), RF-05 (anulación), RF-07/08 (saldos derivados y consolidado), CL-01 a CL-04, CL-08/09/11, P1 (partida doble, inmutabilidad, versión), P5 (multitenancy en cada consulta).

---

## 4. Contrato de la API

Convenciones (P6): rutas en **kebab-case**, sin verbos (el método HTTP expresa la acción), versionadas bajo `/api/v1`. Los montos se serializan como **string** JSON para preservar la precisión Decimal (nunca número flotante). Los mensajes de error van en **español latinoamericano** (CA-09.1/RNF-05). Envoltorio de error uniforme:

```json
{ "detail": [ { "field": "amount", "message": "El monto debe ser mayor que cero" } ] }
```

Códigos de estado estándar: `200`, `201`, `204`, `400` (malformado), `401` (sin sesión válida), `404`, `409` (conflicto: correo duplicado, concurrencia), `422` (validación por campo), `429` (rate limit), `500` (genérico, sin detalles internos).

### Auth — RF-01

- `POST /api/v1/auth/register`
  - Request: `{ "email": "ana@example.com", "password": "min-8-chars" }`
  - `201`: `{ "id": "…", "email": "…", "preferred_currency": "COP" }`
  - `409`: correo ya registrado → `"Este correo ya está registrado"` (CA-01.1)
  - `422`: contraseña corta / correo mal formado, por campo (CA-01.2)
  - `429`: rate limit (P5)
- `POST /api/v1/auth/login`
  - Request: `{ "email", "password" }`
  - `200`: `{ "access_token": "…", "token_type": "bearer", "expires_in": 900, "user": {…} }` + cookie `refresh_token` HttpOnly/Secure/SameSite=Strict (CA-01.3)
  - `401`: `"Correo o contraseña incorrectos"` sin revelar cuál falló (CA-01.4)
- `POST /api/v1/auth/refresh` — cookie refresh → `200` nuevo access + refresh rotado; reutilización detectada → `401` y revocación de la familia (P5)
- `POST /api/v1/auth/logout` — `204`, revoca el refresh (CA-01.5)
- `GET /api/v1/users/me` — `200` perfil (CA-01.6: datos solo del propio usuario)

### Cuentas — RF-02

- `POST /api/v1/accounts` (requiere header `Idempotency-Key: <uuid>`)
  - Request: `{ "name": "Banco Principal", "type": "CASH" | "BANK", "opening_balance": "0.00" }`
  - `201`: `{ "id", "name", "type", "status", "balance", "currency" }` — el opening_balance crea un asiento OPENING
  - `422`: saldo inicial negativo (CA-02.1) o nombre vacío/largo (CA-02.2)
- `GET /api/v1/accounts` → `200`: `[ { "id", "name", "type", "status", "balance", "currency" } ]` (CA-02.3)
- `PATCH /api/v1/accounts/{account_id}` — Request: `{ "name"? }` (CA-02.4) o `{ "status": "INACTIVE" }` (CA-02.5) → `200` | `404` | `409`
- Sin `DELETE`: la desactivación es lógica (P1/RNF-02).

### Categorías — RF-06

- `GET /api/v1/categories?type=INCOME|EXPENSE` → `200`: seed + propias (CA-06)
- `POST /api/v1/categories` (requiere `Idempotency-Key`) — Request: `{ "name", "type" }` → `201` (CA-06.1) | `422` nombre duplicado
- `PATCH /api/v1/categories/{category_id}` — Request: `{ "name"? }` (CA-06.2) o `{ "status": "ACTIVE" | "INACTIVE" }` (CA-06.3, CA-06.4) → `200` | `404` | `422`

### Movimientos — RF-03, RF-04, RF-05, RF-09

- `POST /api/v1/movements` (requiere `Idempotency-Key: <uuid>` — CA-09.2)
  - Request:
    ```json
    {
      "type": "EXPENSE",
      "account_id": "a1000000-…",
      "category_id": "c2000000-…",
      "amount": "150000.00",
      "date": "2026-09-16",
      "note": "Mercado semanal"
    }
    ```
  - `201`: `{ "movement": {…}, "new_balance": "3350000.00" }`
  - `404`: cuenta inexistente · `422`: monto ≤ 0 / más de 2 decimales / fecha futura / saldo insuficiente (con `available_balance`) / categoría inválida · `409`: conflicto de concurrencia
- `POST /api/v1/movements/{movement_id}/void` → `200`: `{ "void_movement": {…}, "new_balance": "…", "negative_balance_warning": false }` | `404` | `422` "El movimiento ya está anulado"
- `GET /api/v1/movements?account_id=&category_id=&date_from=&date_to=&page=1&page_size=50`
  - `200`: `{ "items": [ { "id", "type", "status", "date", "amount", "note", "account", "category" } ], "page", "page_size", "total" }` (RF-08, CA-08.1/08.2/08.3)
  - `page_size` máximo 100 — paginación obligatoria para RNF-06 (10.000 movimientos)

### Balance — RF-07

- `GET /api/v1/balance` → `200`:
  ```json
  {
    "consolidated_balance": "3350000.00",
    "currency": "COP",
    "accounts": [ { "id", "name", "type", "balance" } ]
  }
  ```
  - Solo cuentas activas (CA-07.1); sin cuentas → balance "0.00" (CA-07.3); dos decimales exactos (CA-07.4)

**Cobertura RF**: cada endpoint anota su RF; RF-09 transversal (envelope de errores, idempotencia, atomicidad).

---

## 5. Decisiones técnicas justificadas

Cada decisión indica la alternativa evaluada y descartada, y los RF que impacta.

1. **Backend: FastAPI + Pydantic v2** (confirmado). Alternativas descartadas: Node/TypeScript (Decimal requiere libs adicionales, sin Pydantic nativo para validación de salidas) y NestJS (andamiaje pesado para un MVP). Impacta RF-01..09.
2. **PostgreSQL 16** vs SQLite (sin `SELECT … FOR UPDATE` real ni concurrencia multiusuario robusta — invalida CL-01 bajo carga) vs MySQL (NUMERIC con menos garantías de exactitud y CHECK más débiles). Soporta NUMERIC(19,2), UUID, triggers de inmutabilidad. Impacta P1, RF-03/04/05.
3. **SQLAlchemy 2.0: Core para rutas de escritura + ORM solo para definición de esquema y lecturas simples** vs ORM completo (consultas ocultas, N+1, control pobre de `FOR UPDATE` y `RETURNING`) vs SQL crudo en strings (riesgo de inyección, sin integración con migraciones). Impacta RF-03/04/05, P1.
4. **Dinero: NUMERIC(19,2) + `Decimal` de Python, serializado como string en JSON** vs float (prohibido por P1/RNF-01) vs centavos enteros (rompe la futura multimoneda y resta legibilidad). Los 2 decimales siguen CL-09; la política por moneda sin decimales (COP/CLP) se difiere al spec de multimoneda. Impacta RF-03/04/07, CL-09.
5. **Partida doble con saldo derivado; saldo inicial como asiento OPENING** vs columna `balance` en accounts (viola P1 "el saldo se deriva de sus asientos"; permite deriva y falta de auditoría). La constitución prevalece sobre el supuesto DA-01 del spec: el saldo inicial SÍ aparece en el historial como movimiento de apertura. Impacta RF-02, RF-07, P1.
6. **Concurrencia: híbrido `FOR UPDATE` (serializa la verificación de saldo) + `version` con UPDATE condicional (bloqueo optimista exigido por P1.4)** vs bloqueo optimista puro (ventana check-then-act que permite saldos negativos bajo carreras — viola CL-01) vs pesimista puro sin versión (la constitución exige el campo `version` como contrato de detección de conflictos). Impacta RF-03/04/05, CL-01, P1.4.
7. **Sesiones: JWT de acceso (15 min) + refresh tokens rotativos en cookie HttpOnly/Secure/SameSite=Strict, hasheados (SHA-256) en BD con `family_id` para detectar reutilización** vs sesiones con estado en servidor (P5 de la constitución exige JWT + rotación; además escala horizontal sin almacén compartido) vs refresh en localStorage (expuesto a XSS). Impacta RF-01, P5.
8. **Contraseñas: argon2id** vs bcrypt (más antiguo, sin dureza de memoria configurable) vs PBKDF2 (más débil ante GPU). Impacta RF-01, P5.
9. **Migraciones: Alembic** vs `create_all` (sin historial ni downgrades) vs scripts SQL manuales (sin reproducibilidad). Impacta RF-02..09, despliegues.
10. **Idempotencia por clave, no por igualdad de datos**: header `Idempotency-Key: UUID` generado por el frontend por envío de formulario; la respuesta original se almacena y se reenvía en repeticiones. Resuelve la tensión QA entre CA-09.2 y duplicados legítimos: mismos datos con claves distintas = dos movimientos reales; misma clave = replay sin duplicar (CL-03). Impacta RF-09, CL-03.
11. **Catálogo semilla clonado por usuario al registrarse** (`is_seed = TRUE`) vs filas globales compartidas (imposible renombrar/desactivar por usuario sin afectar a otros). La reactivación se permite para TODAS las categorías (ciclo de vida uniforme; CA-06.4 exige mínimo las predefinidas). Impacta RF-06, CA-06.1..06.4.
12. **Anulación siempre permitida, incluso si deja saldo negativo** (con `negative_balance_warning` en la respuesta) vs bloquear la anulación cuando el saldo resultante es negativo (atrapa al usuario en un historial incorregible; CL-01 regula egresos nuevos, no correcciones de historia). La verdad contable: anular un ingreso ya gastado deja saldo negativo real. Impacta RF-05, CL-11, hallazgo QA B.4.
13. **UUID v4 (`gen_random_uuid()`)** vs IDs secuenciales (exponen volumen y orden de creación entre tenants) vs UUIDv7 (dependencia de versión de PG). Impacta todas las tablas, P5.

---

## 6. Estrategia de pruebas

Pirámide: **unitarias (dominio puro) → integración (PostgreSQL real en contenedor) → E2E (API completa)**, más el gate de CI que exige la constitución (P4: cobertura ≥ 90% en cálculos financieros y flujos transaccionales; el merge se bloquea si fallan pruebas o baja la cobertura).

### 6.1 Unitarias (sin BD — `tests/unit/`)

- `movement_service`: reglas puras — monto > 0 y cuantizado a 2 decimales (CA-03.1, CL-09), fecha futura (CA-03.4/CL-08), categoría por tipo (CA-03.3), saldo insuficiente con `Decimal` exacto (CA-04.2), dirección de líneas INCOME/EXPENSE y balance del asiento (ΣD = ΣC, P1).
- `void_service`: espejo de líneas con direcciones invertidas, idempotencia de anulación (CA-05.3/CL-04), restauración exacta (CA-05.2/CL-11).
- `balance_service`: suma consolidada Decimal exacta; exclusión de cuentas inactivas (CA-07.1); caso sin cuentas (CA-07.3).
- Fixtures de valores límite: `0`, `-1`, `0.001`, `10.999`, saldo exactamente igual al monto, un centavo más, monto máximo `99999999999999999.99`.

### 6.2 Integración (PostgreSQL real — `tests/integration/`)

- **Atomicidad ACID**: simular fallo a mitad de transacción (fixture que lanza excepción entre inserts) y verificar cero filas residuales (CA-09.3).
- **Idempotencia**: mismo `Idempotency-Key` dos veces → una sola fila en `journals`, misma respuesta (CL-03); claves distintas con datos idénticos → dos movimientos (hallazgo QA B.2).
- **Concurrencia**: dos hilos con dos egresos simultáneos sobre saldo que solo alcanza para uno (fixture con barrera de sincronización) → exactamente un `201` y un `409`/`422`, balance consistente (P1.4, CL-01).
- **Inmutabilidad**: `UPDATE`/`DELETE` sobre `journals`/`journal_lines` rechazados por triggers; único cambio permitido `status → VOIDED` (P1).
- **Saldo derivado**: balance de cuenta == apertura + Σ movimientos − Σ anulaciones (verificación de P1); apertura registrada como `OPENING` (decisión 5).
- **Aislamiento multitenancy**: consultas de un usuario con IDs de otro → 404/vacío (CA-01.6, RNF-04); filtro `user_id` impuesto en la capa base de repositorios (P5.2).
- **Desactivación**: cuenta/categoría inactiva rechazada en movimientos nuevos, históricos intactos (CL-05/06); consolidado excluye inactivas (CA-07.1).
- **Anulación**: flujo completo, anulación doble rechazada (CL-04), anulación que deja saldo negativo devuelve `negative_balance_warning` (decisión 12).
- **Catálogo semilla**: al registrarse el usuario recibe las categorías clonadas (CA-06); renombrado/desactivación/reactivación (CA-06.2..06.4).
- **Paginación**: límites de `page_size` y orden `date DESC, created_at DESC` determinista (RF-08, RNF-06).

### 6.3 E2E (API completa — `tests/e2e/`)

- **Viaje feliz (fixture principal)**: registrar → login → crear cuenta con apertura 1.000.000 → ingreso salario 2.500.000 → egreso mercado 150.000 → `GET /balance` == "3350000.00" → anular egreso → balance == "3500000.00" (RF-01..05, RF-07).
- **Contratos y errores**: envelope `{detail:[{field,message}]}` en español para cada caso 422 (CA-09.1); `401` sin token; `429` tras exceder rate limit de login (P5).
- **Rotación de refresh**: uso de cookie refresh → nuevo access; reutilización de un refresh ya rotado → `401` + revocación de familia (P5).
- **Logout**: tras logout, el refresh revocado no emite sesiones nuevas (CA-01.5).

### 6.4 Cobertura y gate de CI

- `pytest` + `pytest-cov`: umbral **≥ 90%** sobre `domain/` y los flujos transaccionales de `api/` (P4); CI falla el build si la cobertura baja o cualquier test falla.
- Matriz de trazabilidad tests → CL-01..CL-11 cubierta por las fixtures de 6.1/6.2.

---

## 7. Trazabilidad: sección → RF

| Sección | RF cubiertos |
|---|---|
| 1. Estructura de módulos | RF-01..RF-09 (distribución por módulo anotada) |
| 2. Modelo de datos | RF-02, RF-03, RF-04, RF-05, RF-06, RF-09; RNF-01/02/03/04; P1, P5 |
| 3. Pseudocódigo | RF-03, RF-04, RF-05, RF-07, RF-08, RF-09; CL-01..04, CL-08/09/11 |
| 4. Contrato API | RF-01..RF-09 (endpoint por endpoint) |
| 5. Decisiones | RF-01, RF-02, RF-03/04/05, RF-06, RF-07, RF-09; CL-01/03/09/11; P1, P4, P5 |
| 6. Estrategia de pruebas | RF-01..RF-09; CL-01..CL-11; RNF-01..07; P4 |

---

## 8. Notas de conformidad constitucional

- **P1**: partida doble explícita, NUMERIC(19,2), inmutabilidad por triggers, saldo derivado, `idempotency_key` único, `version` optimista. ✔
- **P2**: capas api/domain/repositories con dependencias hacia adentro; dominio sin ORM/HTTP. ✔
- **P3**: IA fuera de alcance de este spec; el diseño no crea acoplamiento que impida integrarla luego como adaptador. ✔
- **P4**: pirámide de pruebas y gate de CI con ≥ 90%. ✔
- **P5**: JWT corto + refresh rotativo en cookies, argon2id, multitenancy central en repositorios, rate limit en auth, sin secretos en logs. ✔
- **P6**: código/DDL/endpoints en inglés; mensajes de usuario en español latinoamericano; rutas kebab-case sin verbos. ✔
