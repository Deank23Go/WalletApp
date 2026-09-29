# WalletApp — Constitución del Proyecto

> Este documento es la fuente autoritativa de reglas para el desarrollo de WalletApp. Todo diseño, PR y decisión técnica debe cumplirlo; en caso de conflicto con otra documentación, esta constitución prevalece. Cada principio incluye su criterio de verificación.

## Principio 1 — Integridad contable y aritmética decimal exacta

1. Todo movimiento financiero (ingreso, egreso, transferencia, cuota) se registra como asiento en **partida doble**: débito = crédito, siempre.
2. Los montos se manejan exclusivamente con **aritmética decimal exacta** (`NUMERIC` en BD, `Decimal` en código). **Prohibido** `float`/`double` para dinero.
3. Los asientos confirmados son **inmutables**: corregir = crear un contraasiento, nunca editar o borrar el original.
4. Toda operación financiera porta `idempotency_key`; las escrituras concurrentes usan bloqueo optimista (`version`).

**Verificable con:** cada asiento balancea (Σ débito − Σ crédito = 0); el saldo de cada cuenta se deriva de sus asientos; reenviar la misma clave no duplica; no existe `float` en rutas de dinero.

## Principio 2 — Separación de responsabilidades (Clean Architecture)

1. Capas estrictas: **Frontend (presentación)** → **API (routers/controllers: validación, auth, serialización)** → **Dominio (services/use cases: reglas financieras)** → **Persistencia (repositories)**.
2. Las dependencias apuntan solo hacia adentro: el dominio no importa frameworks, ORM ni HTTP.
3. El backend es la **única fuente de verdad** y la autoridad final de validación; el frontend nunca ejecuta cálculos financieros de autoridad.
4. Procesos pesados (reportes, IA, notificaciones) corren en tareas asíncronas, fuera del hilo de la API.

**Verificable con:** cualquier caso de uso financiero se ejecuta sin servidor web ni base de datos; cada regla de negocio vive en una sola capa.

## Principio 3 — IA desacoplada, contenida y validada

1. La IA es un **servicio externo al dominio**: se consume solo mediante adaptadores y pipelines asíncronos; el core transaccional funciona sin IA.
2. **Opt-in explícito**: el procesamiento de datos del usuario con modelos externos requiere consentimiento explícito y revocable; por defecto está desactivado.
3. **Minimización y sanitización**: los prompts reciben solo los datos estrictamente necesarios, anonimizados; nunca credenciales ni datos de otros usuarios.
4. **Toda salida de IA se valida contra un esquema estricto (Pydantic / JSON Schema)** antes de tocar persistencia; la IA **propone**, el dominio **valida y dispone** — la IA jamás escribe directamente en la BD.
5. Rate limiting y límites de costo en llamadas a modelos; resultados cacheables para evitar re-cómputo.

**Verificable con:** desactivar la IA no rompe ningún flujo crítico; sin opt-in no se envía ningún dato del usuario a modelos externos; una salida malformada o fuera de rango se rechaza sin efectos parciales; ninguna llamada a IA incluye datos de otro tenant.

## Principio 4 — Política de pruebas obligatorias

1. **Cobertura ≥ 90%** en cálculos financieros (cuotas, intereses, amortización, proyecciones, simuladores), asientos y endpoints transaccionales.
2. Toda regla financiera nueva exige tests unitarios con **casos límite** (residuo de cuotas, idempotencia, concurrencia, montos inválidos).
3. Todo endpoint tiene tests de contrato (request/response y códigos de estado); los flujos críticos (auth, transacción, pago de cuota, alertas) tienen tests E2E.
4. **CI bloquea el merge** si un test falla o la cobertura requerida baja.

**Verificable con:** reporte de cobertura automatizado en CI; un PR sin tests para lógica financiera se rechaza.

## Principio 5 — Seguridad y privacidad de datos

1. **Sesiones**: JWT de acceso de corta vida + refresh tokens rotativos en cookies `HttpOnly`/`Secure`/`SameSite`; contraseñas con `argon2`/`bcrypt`.
2. **Multitenancy**: aislamiento estricto por `user_id` en **toda** consulta, impuesto centralmente (repositorio/ORM), nunca por disciplina del programador.
3. **Sanitización**: validación de entrada en la frontera de la API, escape de salidas, y nunca registrar secretos o credenciales en logs.
4. TLS 1.3 en tránsito, cifrado en reposo para datos sensibles, y rate limiting en endpoints críticos (auth e IA).

**Verificable con:** un test de aislamiento que intenta acceder a datos de otro tenant falla; auditoría automática (linter/hook) que detecta queries sin filtro de tenant; un refresh token revocado no puede emitir sesiones nuevas.

## Principio 6 — Idioma y estilo

1. **Código, variables, comentarios, commits, endpoints y documentación técnica: inglés.**
2. **UI, mensajes de usuario y errores de negocio: español latinoamericano** (formal, sin regionalismos ambiguos).
3. Commits en **Conventional Commits** (`feat:`, `fix:`, `test:`, `docs:`) con mensajes en inglés.
4. Endpoints REST versionados (`/api/v1/...`) en kebab-case, sin verbos (el método HTTP expresa la acción); formatos numéricos y de fecha normalizados en la capa de presentación.

**Verificable con:** lint de commits en CI (commitlint); la revisión de PR valida idioma de UI vs. código; auditoría de endpoints contra el estilo definido.
