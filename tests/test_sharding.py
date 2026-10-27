"""Проверяет маршрутизацию и единый REST API пятой лабораторной работы."""

import json
from urllib.parse import unquote, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from src.sharding.router import ShardRouter, create_router_app
from src.structures import Shard


SHARDS = [
    Shard("shard-0", "http://shard-0"),
    Shard("shard-1", "http://shard-1"),
]


def test_known_sha256_vectors_are_stable() -> None:
    """
    Проверяет известные результаты SHA-256 по модулю два.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    router = ShardRouter(SHARDS)

    assert router.route("alpha").name == "shard-0"
    assert router.route("beta").name == "shard-1"
    assert router.route("ключ").name == "shard-0"
    assert router.route("lab5-one").name == "shard-1"


def test_configuration_requires_two_unique_shards() -> None:
    """
    Проверяет ограничения фиксированной топологии сегментов.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    with pytest.raises(ValueError):
        ShardRouter(SHARDS[:1])
    with pytest.raises(ValueError):
        ShardRouter([
            Shard("same", "http://shard-0"),
            Shard("same", "http://shard-1"),
        ])
    with pytest.raises(ValueError):
        create_router_app(SHARDS, request_timeout=float("inf"))


def test_crud_is_forwarded_to_exactly_one_primary() -> None:
    """
    Проверяет CRUD через маршрутизатор и изоляцию данных сегментов.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    states: dict[str, dict[str, object]] = {"shard-0": {}, "shard-1": {}}
    calls: list[tuple[str, str, str]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        """
        Имитирует публичный REST API двух primary.

        Parameters:
            request (httpx.Request): Перенаправленный запрос.

        Returns:
            httpx.Response: Ответ выбранного тестового primary.

        Fallbacks:
            Отсутствующий ключ возвращает HTTP 404.
        """
        host = request.url.host
        path = request.url.path
        calls.append((request.method, host, path))
        state = states[host]
        if path == "/kv":
            return httpx.Response(200, json={"keys": sorted(state)})

        key = unquote(path.removeprefix("/kv/"))
        if request.method == "PUT":
            state[key] = json.loads(request.content)["value"]
            return httpx.Response(204)
        if request.method == "DELETE":
            if key not in state:
                return httpx.Response(404, json={"detail": "Ключ не найден"})
            del state[key]
            return httpx.Response(204)
        if key not in state:
            return httpx.Response(404, json={"detail": "Ключ не найден"})
        return httpx.Response(200, json={"value": state[key]})

    client = TestClient(create_router_app(
        SHARDS,
        transport=httpx.MockTransport(handle_request),
    ))

    assert client.put("/kv/alpha", json={"value": 1}).status_code == 204
    assert client.put("/kv/beta", json={"value": {"v": 2}}).status_code == 204
    assert states == {
        "shard-0": {"alpha": 1},
        "shard-1": {"beta": {"v": 2}},
    }
    assert client.get("/kv/alpha").json() == {"value": 1}
    assert client.get("/kv/beta").json() == {"value": {"v": 2}}
    assert client.delete("/kv/alpha").status_code == 204
    assert "alpha" not in states["shard-0"]

    router = ShardRouter(SHARDS)
    assert all(
        host == urlparse(router.route(path.rsplit("/", 1)[-1]).endpoint).hostname
        for method, host, path in calls
        if path != "/kv"
    )


def test_list_keys_returns_sorted_unique_union() -> None:
    """
    Проверяет полное детерминированное объединение списков сегментов.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    def handle_request(request: httpx.Request) -> httpx.Response:
        """
        Возвращает пересекающиеся списки тестовых сегментов.

        Parameters:
            request (httpx.Request): Запрос списка ключей.

        Returns:
            httpx.Response: Список соответствующего сегмента.

        Fallbacks:
            Не предусмотрены.
        """
        keys = (
            ["zeta", "shared"]
            if request.url.host == "shard-0"
            else ["alpha", "shared"]
        )
        return httpx.Response(200, json={"keys": keys})

    client = TestClient(create_router_app(
        SHARDS,
        transport=httpx.MockTransport(handle_request),
    ))

    assert client.get("/kv").json() == {
        "keys": ["alpha", "shared", "zeta"],
    }


def test_list_keys_rejects_partial_result() -> None:
    """
    Проверяет HTTP 503 вместо частичного списка при сбое сегмента.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Адрес недоступного сегмента не раскрывается.
    """
    def handle_request(request: httpx.Request) -> httpx.Response:
        """
        Имитирует недоступность второго сегмента.

        Parameters:
            request (httpx.Request): Запрос списка ключей.

        Returns:
            httpx.Response: Список первого сегмента.

        Fallbacks:
            Для второго сегмента вызывает ConnectError.
        """
        if request.url.host == "shard-1":
            raise httpx.ConnectError("secret shard address", request=request)
        return httpx.Response(200, json={"keys": ["available"]})

    response = TestClient(create_router_app(
        SHARDS,
        transport=httpx.MockTransport(handle_request),
    )).get("/kv")

    assert response.status_code == 503
    assert response.json() == {"detail": "Хранилище недоступно"}
    assert "secret" not in response.text


def test_diagnostic_endpoint_does_not_contact_nodes() -> None:
    """
    Проверяет локальный диагностический выбор сегмента.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    def reject_request(request: httpx.Request) -> httpx.Response:
        """
        Запрещает любой сетевой запрос в диагностическом сценарии.

        Parameters:
            request (httpx.Request): Неожиданный запрос.

        Returns:
            httpx.Response: Функция не должна завершиться нормально.

        Fallbacks:
            Всегда вызывает AssertionError.
        """
        raise AssertionError(f"Неожиданный запрос: {request.url}")

    client = TestClient(create_router_app(
        SHARDS,
        transport=httpx.MockTransport(reject_request),
    ))

    assert client.get("/shards/alpha").json() == {"shard": "shard-0"}
    assert client.get("/shards/beta").json() == {"shard": "shard-1"}
