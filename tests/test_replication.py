"""Проверяет журнал и асинхронную репликацию четвёртой работы."""

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.errors import ReplicationError
from src.replication import ReplicationManager
from src.storage import JsonStorage
from src.store import KeyValueStore
from src.structures import Mutation, MutationType, NodeRole


def test_primary_writes_ordered_durable_log(tmp_path: Path) -> None:
    """
    Проверяет порядок журнала и восстановление номера после перезапуска.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    data_path = tmp_path / "primary.json"
    log_path = tmp_path / "primary.jsonl"
    manager = ReplicationManager(
        KeyValueStore(JsonStorage(data_path)),
        NodeRole.PRIMARY,
        log_path,
    )

    manager.put("alpha", {"version": 1})
    manager.put("alpha", {"version": 2})
    manager.delete("alpha")

    restarted = ReplicationManager(
        KeyValueStore(JsonStorage(data_path)),
        NodeRole.PRIMARY,
        log_path,
    )

    assert restarted.current_sequence == 3
    assert [
        mutation.operation for mutation in restarted.operations_after(0)
    ] == [MutationType.PUT, MutationType.PUT, MutationType.DELETE]


def test_replica_rejects_public_writes(tmp_path: Path) -> None:
    """
    Проверяет HTTP 403 и неизменность состояния реплики.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    application = create_app(
        tmp_path / "replica.json",
        role=NodeRole.REPLICA,
        replication_log=tmp_path / "replica.jsonl",
        primary_url="http://primary:8000",
    )
    client = TestClient(application)

    assert client.put("/kv/blocked", json={"value": 1}).status_code == 403
    assert client.delete("/kv/blocked").status_code == 403
    assert client.get("/kv").json() == {"keys": []}


def test_replica_applies_idempotently_and_restores_progress(
    tmp_path: Path,
) -> None:
    """
    Проверяет идемпотентное применение и продолжение после перезапуска.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    data_path = tmp_path / "replica.json"
    log_path = tmp_path / "replica.jsonl"
    first = Mutation(1, MutationType.PUT, "item", {"version": 1})
    second = Mutation(2, MutationType.DELETE, "item")
    manager = ReplicationManager(
        KeyValueStore(JsonStorage(data_path)),
        NodeRole.REPLICA,
        log_path,
        "http://primary:8000",
    )

    manager.apply([first, second])
    manager.apply([first, second])

    restarted_store = KeyValueStore(JsonStorage(data_path))
    restarted = ReplicationManager(
        restarted_store,
        NodeRole.REPLICA,
        log_path,
        "http://primary:8000",
    )
    restarted.apply(
        [Mutation(3, MutationType.PUT, "restored", True)]
    )

    assert restarted.current_sequence == 3
    assert restarted_store.get("restored") is True


def test_replica_stops_on_gap_or_conflict(tmp_path: Path) -> None:
    """
    Проверяет явный отказ при разрыве и конфликте номера операции.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    manager = ReplicationManager(
        KeyValueStore(JsonStorage(tmp_path / "replica.json")),
        NodeRole.REPLICA,
        tmp_path / "replica.jsonl",
        "http://primary:8000",
    )

    with pytest.raises(ReplicationError):
        manager.apply([Mutation(2, MutationType.PUT, "gap", 1)])

    first = Mutation(1, MutationType.PUT, "key", 1)
    manager.apply([first])
    with pytest.raises(ReplicationError):
        manager.apply([Mutation(1, MutationType.PUT, "key", 2)])


def test_operation_feed_is_bounded_and_sorted(tmp_path: Path) -> None:
    """
    Проверяет курсор и ограничение пачки внутреннего endpoint.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    client = TestClient(
        create_app(
            tmp_path / "primary.json",
            replication_log=tmp_path / "primary.jsonl",
            batch_size=2,
        )
    )
    for index in range(3):
        client.put(f"/kv/key-{index}", json={"value": index})

    response = client.get("/replication/operations", params={"after": 0})

    assert response.status_code == 200
    assert response.json()["primary_sequence"] == 3
    assert [
        item["sequence"] for item in response.json()["operations"]
    ] == [1, 2]


def test_replica_pulls_multiple_batches(tmp_path: Path) -> None:
    """
    Проверяет догоняющую синхронизацию через несколько ограниченных пачек.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    primary_app = create_app(
        tmp_path / "primary.json",
        replication_log=tmp_path / "primary.jsonl",
        batch_size=1,
    )
    primary_client = TestClient(primary_app)
    primary_client.put("/kv/one", json={"value": 1})
    primary_client.put("/kv/two", json={"value": 2})

    replica_store = KeyValueStore(JsonStorage(tmp_path / "replica.json"))
    replica = ReplicationManager(
        replica_store,
        NodeRole.REPLICA,
        tmp_path / "replica.jsonl",
        "http://primary",
        transport=httpx.ASGITransport(app=primary_app),
    )

    asyncio.run(replica.synchronize_once())
    asyncio.run(replica.synchronize_once())

    assert replica.current_sequence == 2
    assert replica_store.list_keys() == ["one", "two"]
    assert replica.status().lag == 0

def test_replica_recovers_after_temporary_primary_outage(
    tmp_path: Path,
) -> None:
    """
    Проверяет обновление статуса и повторную синхронизацию после сбоя.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    attempts = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        """
        Имитирует недоступность primary при первом обращении.

        Parameters:
            request (httpx.Request): Запрос реплики к primary.

        Returns:
            httpx.Response: Успешная пачка при повторном обращении.

        Fallbacks:
            Первое обращение вызывает ConnectError.
        """
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("Основной узел недоступен", request=request)
        return httpx.Response(
            200,
            json={
                "primary_sequence": 1,
                "operations": [
                    {
                        "sequence": 1,
                        "operation": "put",
                        "key": "recovered",
                        "value": True,
                    }
                ],
            },
        )

    replica_store = KeyValueStore(JsonStorage(tmp_path / "replica.json"))
    replica = ReplicationManager(
        replica_store,
        NodeRole.REPLICA,
        tmp_path / "replica.jsonl",
        "http://primary",
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(ReplicationError):
        asyncio.run(replica.synchronize_once())
    assert replica.status().healthy is False

    asyncio.run(replica.synchronize_once())

    assert replica.status().healthy is True
    assert replica.status().lag == 0
    assert replica_store.get("recovered") is True
