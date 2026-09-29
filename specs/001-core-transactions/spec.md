# SPEC-001 — Núcleo Transaccional: Cuentas, Movimientos y Balance

**Módulo**: Autenticación básica, Cuentas (Efectivo/Banco), Movimientos (Ingresos/Egresos) y Balance Consolidado
**Versión**: 1.0
**Estado**: Borrador
**Fecha**: 2026-09-21

---

## 1. Contexto y Objetivo

WalletApp es una plataforma de gestión de finanzas personales. Esta primera funcionalidad establece el núcleo transaccional mínimo: un usuario puede crear su cuenta de acceso, registrar sus cuentas financieras (efectivo y banco), añadir movimientos de ingresos y egresos clasificados por categorías, y consultar su balance actual consolidado.

**Objetivo**: dar al usuario un control contable básico, transparente y confiable de su dinero: cada movimiento queda registrado, corregir un error nunca altera el historial, y el balance mostrado siempre corresponde a la suma exacta de los movimientos registrados.

**Alcance mínimo deliberado**: sin tarjetas de crédito, sin transferencias entre cuentas, sin multimoneda y sin funciones de IA. Todo eso llega en funcionalidades posteriores.

---

## 2. Usuarios

| Rol | Descripción |
|-----|-------------|
| **Usuario autenticado** | Persona que gestiona sus finanzas personales. Crea cuentas, registra movimientos y consulta su balance. Solo accede a su propia información. |
| **Visitante** | Persona no autenticada que solo puede registrarse o iniciar sesión. |

---

## 3. Historias de Usuario

| ID | Historia |
|----|----------|
| HU-01 | Como visitante, quiero registrarme con mi correo y una contraseña, e iniciar sesión después, para acceder de forma segura a mi información financiera. |
| HU-02 | Como usuario, quiero crear cuentas de efectivo y banco con un nombre y un saldo inicial opcional, para reflejar mi situación financiera real. |
| HU-03 | Como usuario, quiero registrar un ingreso indicando cuenta de destino, categoría, monto, fecha y nota, para mantener al día el dinero que recibo. |
| HU-04 | Como usuario, quiero registrar un egreso indicando cuenta de origen, categoría, monto, fecha y nota, para llevar control de mis gastos. |
| HU-05 | Como usuario, quiero anular un movimiento que registré con datos erróneos, para que el sistema genere la corrección automáticamente sin alterar el historial. |
| HU-06 | Como usuario, quiero usar un catálogo de categorías predefinido y crear, renombrar o desactivar las mías, para clasificar mis movimientos a mi manera. |
| HU-07 | Como usuario, quiero ver mi balance consolidado y el saldo de cada cuenta, para conocer mi situación financiera de un vistazo. |
| HU-08 | Como usuario, quiero consultar el historial de mis movimientos ordenados por fecha y filtrarlos por cuenta, categoría o rango de fechas, para rastrear cada registro. |

---

## 4. Requisitos Funcionales

> Los criterios de aceptación usan notación EARS en español: **Cuando** (evento), **Si** (condición), **Mientras** (estado).

### RF-01 — Registro e inicio de sesión
**Cuando** el visitante envía un formulario de registro con correo y contraseña válidos, **el sistema debe** crear su cuenta de usuario y dejarlo listo para iniciar sesión.

**Criterios de aceptación**:
- CA-01.1: **Si** el correo ya está registrado, **el sistema debe** rechazar el registro con el mensaje "Este correo ya está registrado".
- CA-01.2: **Si** la contraseña no cumple la longitud mínima exigida, **el sistema debe** rechazar el registro indicando el campo y la causa.
- CA-01.3: **Cuando** el usuario ingresa sus credenciales correctas, **el sistema debe** iniciar su sesión y mostrarle su panel financiero.
- CA-01.4: **Si** las credenciales son incorrectas, **el sistema debe** mostrar "Correo o contraseña incorrectos" sin revelar cuál de los dos datos falló.
- CA-01.5: **Cuando** el usuario cierra sesión, **el sistema debe** impedir el acceso a su información hasta un nuevo inicio de sesión.
- CA-01.6: **Mientras** un usuario esté autenticado, **el sistema debe** mostrarle únicamente sus propios datos, nunca los de otro usuario.

### RF-02 — Gestión de cuentas
**Cuando** el usuario crea una cuenta con nombre, tipo (efectivo o banco) y saldo inicial opcional, **el sistema debe** registrarla y dejarla disponible para movimientos.

**Criterios de aceptación**:
- CA-02.1: **Si** el saldo inicial es negativo, **el sistema debe** rechazar la creación con mensaje descriptivo.
- CA-02.2: **Si** el nombre está vacío o excede la longitud máxima, **el sistema debe** rechazar la creación indicando el campo y la causa.
- CA-02.3: **Cuando** el usuario lista sus cuentas, **el sistema debe** mostrar nombre, tipo, saldo actual y estado (activa/inactiva) de cada una.
- CA-02.4: **Cuando** el usuario renombra una cuenta, **el sistema debe** conservar intactos sus movimientos históricos.
- CA-02.5: **Cuando** el usuario desactiva una cuenta, **el sistema debe** impedir usarla en nuevos movimientos sin alterar sus movimientos históricos.

### RF-03 — Registro de ingreso
**Cuando** el usuario envía un ingreso con cuenta de destino, categoría de ingreso, monto, fecha y nota opcional, **el sistema debe** registrarlo y aumentar el saldo de la cuenta de destino en el monto exacto.

**Criterios de aceptación**:
- CA-03.1: **Si** el monto es cero o negativo, **el sistema debe** rechazar el movimiento con el mensaje "El monto debe ser mayor que cero".
- CA-03.2: **Si** la cuenta de destino no existe o está desactivada, **el sistema debe** rechazar el movimiento.
- CA-03.3: **Si** la categoría no existe o no es de tipo ingreso, **el sistema debe** rechazar el movimiento.
- CA-03.4: **Si** la fecha es futura, **el sistema debe** rechazar el movimiento indicando el campo y la causa.
- CA-03.5: **Cuando** el ingreso queda registrado, **el sistema debe** reflejarlo de inmediato en el saldo de la cuenta y en el balance consolidado.

### RF-04 — Registro de egreso
**Cuando** el usuario envía un egreso con cuenta de origen, categoría de egreso, monto, fecha y nota opcional, **el sistema debe** registrarlo y disminuir el saldo de la cuenta de origen en el monto exacto.

**Criterios de aceptación**:
- CA-04.1: Aplican los mismos criterios de validación de monto, cuenta, categoría y fecha que RF-03.
- CA-04.2: **Si** el monto del egreso es mayor que el saldo disponible de la cuenta de origen, **el sistema debe** rechazarlo con el mensaje "Saldo insuficiente en la cuenta" y mostrar el saldo disponible al usuario.
- CA-04.3: **Cuando** el egreso queda registrado, **el sistema debe** reflejarlo de inmediato en el saldo de la cuenta y en el balance consolidado.

### RF-05 — Anulación de movimientos
**Cuando** el usuario anula un movimiento confirmado, **el sistema debe** registrar automáticamente su contramovimiento inverso y marcar el original como anulado, sin editar ni eliminar el registro original.

**Criterios de aceptación**:
- CA-05.1: El movimiento original permanece visible en el historial con su estado de anulado.
- CA-05.2: El contramovimiento restaura el saldo de la cuenta afectada al valor exacto anterior al movimiento anulado.
- CA-05.3: **Si** el usuario intenta anular un movimiento ya anulado, **el sistema debe** rechazar la operación con mensaje descriptivo.
- CA-05.4: **Cuando** se anula un movimiento, **el sistema debe** excluir tanto el original como su contramovimiento de los totales de ingresos y egresos del balance.

### RF-06 — Catálogo de categorías
**Cuando** un usuario accede por primera vez, **el sistema debe** proveer un catálogo predefinido de categorías de ingreso y egreso en español latinoamericano.

**Criterios de aceptación**:
- CA-06.1: **Cuando** el usuario crea una categoría propia, **el sistema debe** asociarla a un tipo (ingreso o egreso) y dejarla disponible en los formularios.
- CA-06.2: **Cuando** el usuario renombra una categoría, **el sistema debe** aplicar el nuevo nombre también en el historial visible.
- CA-06.3: **Cuando** el usuario desactiva una categoría, **el sistema debe** impedir usarla en nuevos movimientos sin alterar los movimientos históricos.
- CA-06.4: **Si** la categoría desactivada es una del catálogo predefinido, **el sistema debe** permitir reactivarla.

### RF-07 — Balance consolidado
**Mientras** el usuario se encuentra en su panel, **el sistema debe** mostrar su balance actual consolidado como la suma exacta de los saldos de sus cuentas activas, junto con el saldo individual de cada cuenta.

**Criterios de aceptación**:
- CA-07.1: El balance consolidado solo incluye cuentas activas.
- CA-07.2: El balance se recalcula automáticamente después de cada movimiento, ingreso o anulación, sin recargar la página.
- CA-07.3: **Si** el usuario no tiene cuentas, **el sistema debe** mostrar el balance en cero y una invitación a crear su primera cuenta.
- CA-07.4: El balance se presenta con la moneda configurada por el usuario y con dos decimales exactos, sin redondeos de punto flotante.

### RF-08 — Historial de movimientos
**Cuando** el usuario consulta su historial, **el sistema debe** mostrar sus movimientos ordenados por fecha descendente, indicando tipo (ingreso/egreso/anulado), cuenta, categoría, monto, fecha y nota.

**Criterios de aceptación**:
- CA-08.1: Los filtros por cuenta, categoría y rango de fechas son combinables.
- CA-08.2: **Cuando** el usuario limpia los filtros, **el sistema debe** restaurar el historial completo.
- CA-08.3: **Si** no hay movimientos para los filtros aplicados, **el sistema debe** mostrar "Sin movimientos para los filtros aplicados".
- CA-08.4: Los movimientos anulados se distinguen visualmente de los vigentes.

### RF-09 — Validación y rechazo estricto
**Si** el usuario envía datos inválidos en cualquier formulario, **el sistema debe** rechazar la operación completa, no persistir datos parciales y mostrar un mensaje en español latinoamericano que identifique el campo y la causa.

**Criterios de aceptación**:
- CA-09.1: El mensaje de error es específico por campo (por ejemplo: "El monto debe ser mayor que cero", "El nombre es obligatorio").
- CA-09.2: **Si** el usuario reenvía el mismo formulario dos veces, **el sistema debe** registrar el movimiento una sola vez.
- CA-09.3: **Si** la operación falla, **el sistema debe** devolver la cuenta a su estado anterior sin cambios parciales de saldo.

---

## 5. Requisitos No Funcionales

| ID | Requisito |
|----|-----------|
| RNF-01 | **Precisión numérica**: todos los montos y saldos se calculan con aritmética decimal exacta. Nunca punto flotante. |
| RNF-02 | **Inmutabilidad**: los movimientos confirmados no se editan ni eliminan; toda corrección se hace por anulación con contramovimiento. |
| RNF-03 | **Idempotencia**: reenviar la misma operación no duplica movimientos ni altera saldos. |
| RNF-04 | **Privacidad multiusuario**: cada usuario solo puede ver y operar sus propios datos; ningún flujo permite acceder a información de otro usuario. |
| RNF-05 | **Idioma**: interfaz y mensajes de error en español latinoamericano, formal y sin regionalismos ambiguos. |
| RNF-06 | **Rendimiento**: el balance consolidado y el historial filtrado responden en menos de 500 ms para volúmenes de hasta 10.000 movimientos. |
| RNF-07 | **Seguridad de sesión**: el acceso a toda la funcionalidad requiere sesión activa; las credenciales se almacenan protegidas con cifrado. |

---

## 6. Casos Límite

| # | Caso | Comportamiento esperado |
|---|------|------------------------|
| CL-01 | Egreso por un monto mayor al saldo disponible | Se rechaza con "Saldo insuficiente en la cuenta" y se muestra el saldo disponible. |
| CL-02 | Monto cero o negativo en ingreso o egreso | Se rechaza con "El monto debe ser mayor que cero". |
| CL-03 | Reenvío del mismo formulario (doble clic, reintento) | El movimiento se registra una sola vez. |
| CL-04 | Anular un movimiento ya anulado | Se rechaza con mensaje descriptivo. |
| CL-05 | Desactivar una cuenta con movimientos históricos | La cuenta queda inactiva, no acepta movimientos nuevos y sus movimientos históricos permanecen intactos. |
| CL-06 | Desactivar una categoría con movimientos históricos | La categoría no acepta movimientos nuevos y sus movimientos históricos conservan su clasificación. |
| CL-07 | Crear cuenta sin saldo inicial | La cuenta inicia en cero y acepta movimientos normalmente. |
| CL-08 | Registrar movimiento con fecha futura | Se rechaza indicando el campo y la causa. |
| CL-09 | Movimiento con monto de más de dos decimales (ej. 10,999) | Se rechaza indicando el formato esperado. |
| CL-10 | Usuario sin movimientos | El balance muestra los saldos iniciales de sus cuentas y el historial indica "Sin movimientos para los filtros aplicados". |
| CL-11 | Anular un ingreso o egreso que afecta el balance | El balance vuelve exactamente al valor anterior al movimiento anulado. |

---

## 7. Fuera de Alcance (este spec)

> Estas funcionalidades serán cubiertas por specs futuros y están garantizadas en el roadmap de WalletApp.

- Tarjetas de crédito, compras a cuotas y fechas de corte.
- Préstamos y pasivos.
- Transferencias entre cuentas del mismo usuario.
- Multimoneda y conversión cambiaria.
- Suscripciones y pagos recurrentes.
- Presupuestos y alertas de límite de gasto.
- Notificaciones y recordatorios.
- Funciones de IA (OCR de recibos, asistente conversacional, categorización inteligente).
- Inicio de sesión con proveedores externos (OAuth/Google).
- Exportación e importación de extractos bancarios.
- Reportes en PDF o Excel.

---

## 8. Criterios de Finalización

Este spec se considera completo cuando:

- [ ] Todos los RF (01–09) están implementados y pasan sus criterios de aceptación.
- [ ] Los RNF (01–07) se verifican mediante pruebas automatizadas.
- [ ] Los casos límite (CL-01 a CL-11) tienen pruebas específicas.
- [ ] La cobertura de pruebas en cálculos financieros y flujos transaccionales es ≥ 90%, según la constitución del proyecto.
- [ ] La interfaz muestra toda la información y los mensajes de error en español latinoamericano.
- [ ] Se verifica el aislamiento de datos: ningún usuario puede acceder a información de otro.

---

## 9. Dudas Abiertas

| # | Duda | Estado |
|---|------|--------|
| DA-01 | ¿El saldo inicial de una cuenta debe verse como un movimiento de apertura en el historial o solo como un dato de la cuenta? (Asumido: solo como dato de la cuenta). | [NECESITA ACLARACIÓN] |
| DA-02 | ¿Se permiten fechas futuras en los movimientos? (Asumido: no se permiten). | [NECESITA ACLARACIÓN] |
| DA-03 | ¿El balance consolidado debe incluir las cuentas desactivadas? (Asumido: solo cuentas activas; el saldo de las desactivadas se ve en el detalle de la cuenta). | [NECESITA ACLARACIÓN] |
| DA-04 | ¿El registro de usuario exige verificación de correo en este MVP? (Asumido: no en este spec; se evalúa en el spec de autenticación avanzada). | [NECESITA ACLARACIÓN] |
| DA-05 | ¿Debe existir un límite de cuentas o categorías por usuario? (Asumido: sin límite en el MVP). | [NECESITA ACLARACIÓN] |
