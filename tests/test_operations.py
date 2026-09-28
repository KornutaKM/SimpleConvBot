import pytest

from simpleconvbot.operations import OperationDefinition, OperationRegistry, UnknownOperation


def test_registry_resolves_exact_version() -> None:
    operation = OperationDefinition("test.noop", 1, "test")
    registry = OperationRegistry([operation])

    assert registry.get("test.noop", 1) is operation


def test_registry_rejects_unknown_version() -> None:
    registry = OperationRegistry([OperationDefinition("test.noop", 1, "test")])

    with pytest.raises(UnknownOperation):
        registry.get("test.noop", 2)


def test_registry_rejects_duplicate_identity() -> None:
    operation = OperationDefinition("test.noop", 1, "test")

    with pytest.raises(ValueError, match="duplicate"):
        OperationRegistry([operation, operation])


@pytest.mark.parametrize("operation_id", ["Bad Name", "TEST.NOOP", "../noop", ""])
def test_operation_id_is_bounded_identifier(operation_id: str) -> None:
    with pytest.raises(ValueError):
        OperationDefinition(operation_id, 1, "test")
