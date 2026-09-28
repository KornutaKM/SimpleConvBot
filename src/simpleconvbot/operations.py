from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_OPERATION_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class UnknownOperation(KeyError):
    """Raised when an operation identity is not registered."""


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    operation_id: str
    version: int
    worker_family: str

    def __post_init__(self) -> None:
        if not _OPERATION_ID_PATTERN.fullmatch(self.operation_id):
            raise ValueError("operation_id must be a stable lowercase identifier")
        if self.version <= 0:
            raise ValueError("operation version must be greater than zero")
        if not self.worker_family.strip():
            raise ValueError("worker_family must not be empty")


class OperationRegistry:
    def __init__(self, definitions: Iterable[OperationDefinition] = ()) -> None:
        items = tuple(definitions)
        indexed = {(item.operation_id, item.version): item for item in items}
        if len(indexed) != len(items):
            raise ValueError("duplicate operation identity/version")
        self._definitions = indexed

    def get(self, operation_id: str, version: int) -> OperationDefinition:
        try:
            return self._definitions[(operation_id, version)]
        except KeyError as exc:
            raise UnknownOperation(f"{operation_id}@{version}") from exc
