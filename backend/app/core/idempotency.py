from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.errors import DomainConflictError, IdempotencyError
from app.domain.ports import JsonObject, StoredResponse


class ResponseStore(Protocol):
    def claim(self, idempotency_key: uuid.UUID) -> bool: ...
    def complete(self, idempotency_key: uuid.UUID, *, status_code: int, body: JsonObject) -> bool: ...
    def load(self, idempotency_key: uuid.UUID) -> StoredResponse | None: ...


class IdempotencyCoordinator:
    def __init__(self, responses: ResponseStore, *, operation: str) -> None:
        self._responses = responses
        self._operation = operation

    def claim_or_replay(self, idempotency_key: uuid.UUID) -> StoredResponse | None:
        if self._responses.claim(idempotency_key):
            return None
        stored = self._responses.load(idempotency_key)
        if stored is None:
            raise IdempotencyError("La operación con esta clave todavía está en proceso")
        if stored.body.get("operation") != self._operation:
            raise DomainConflictError(
                "La clave de idempotencia ya fue utilizada en otra operación",
                field="Idempotency-Key",
            )
        response = stored.body.get("response")
        if not isinstance(response, dict):
            raise IdempotencyError("La respuesta idempotente almacenada no es válida")
        return StoredResponse(status_code=stored.status_code, body=response)

    def complete(self, idempotency_key: uuid.UUID, *, status_code: int, response: JsonObject) -> None:
        body: JsonObject = {"operation": self._operation, "response": response}
        if not self._responses.complete(idempotency_key, status_code=status_code, body=body):
            raise IdempotencyError("No fue posible completar la operación idempotente")
