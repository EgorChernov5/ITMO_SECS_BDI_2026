"""Проверяет архитектурные контракты первой лабораторной работы."""

from inspect import isabstract, signature

import pytest

from src.errors import (
    KeyNotFoundError,
    MiniKVError,
    NodeUnavailableError,
    PersistenceError,
)
from src.interfaces import (
    IKeyValueStore,
    IReplicationManager,
    IShardRouter,
    IStorageEngine,
)
from src.stubs import KeyValueStoreStub, StorageEngineStub


def test_interfaces_are_abstract() -> None:
    """
    Проверяет невозможность создать интерфейсы напрямую.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    interfaces = (
        IKeyValueStore,
        IStorageEngine,
        IReplicationManager,
        IShardRouter,
    )

    assert all(isabstract(interface) for interface in interfaces)
    for interface in interfaces:
        with pytest.raises(TypeError):
            interface()


def test_store_operation_signatures_are_stable() -> None:
    """
    Проверяет имена параметров четырёх публичных операций.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    expected_parameters = {
        "put": ("self", "key", "value"),
        "get": ("self", "key"),
        "delete": ("self", "key"),
        "list_keys": ("self",),
    }

    for method_name, parameter_names in expected_parameters.items():
        method_signature = signature(getattr(IKeyValueStore, method_name))
        assert tuple(method_signature.parameters) == parameter_names
        assert method_signature.return_annotation is not method_signature.empty


def test_supporting_interface_methods_are_available() -> None:
    """
    Проверяет наличие методов вспомогательных интерфейсов.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    expected_methods = {
        IStorageEngine: ("load", "save"),
        IReplicationManager: ("publish", "apply"),
        IShardRouter: ("route",),
    }

    for interface, method_names in expected_methods.items():
        for method_name in method_names:
            method_signature = signature(getattr(interface, method_name))
            assert method_signature.return_annotation is not method_signature.empty


def test_domain_errors_share_project_base_error() -> None:
    """
    Проверяет общую иерархию ошибок предметной области.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    errors = (KeyNotFoundError, PersistenceError, NodeUnavailableError)

    assert all(issubclass(error, MiniKVError) for error in errors)
    assert all(issubclass(error, Exception) for error in errors)


def test_stub_rejects_empty_key_and_has_no_storage_behavior() -> None:
    """
    Проверяет граничную валидацию и явный отказ заглушек.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    store = KeyValueStoreStub(StorageEngineStub())

    with pytest.raises(ValueError):
        store.get("")
    with pytest.raises(NotImplementedError):
        store.get("existing-format-key")
    with pytest.raises(NotImplementedError):
        store.list_keys()
