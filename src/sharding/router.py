"""Реализует стабильную маршрутизацию и единый REST API сегментов."""

import hashlib
import os
from math import isfinite
from urllib.parse import quote, urlparse

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from src.api.structures import (
    HealthResponse,
    KeysResponse,
    PutRequest,
    ShardResponse,
    ValueResponse,
)
from src.constants import DEFAULT_SHARD_REQUEST_TIMEOUT, MIN_KEY_LENGTH
from src.errors import KeyNotFoundError, NodeUnavailableError, PersistenceError
from src.interfaces import IKeyValueStore, IShardRouter
from src.structures import JsonValue, Shard


class ShardRouter(IShardRouter):
    """
    Выбирает один из двух настроенных сегментов по SHA-256 ключа.

    Attributes:
        shards (tuple[Shard, Shard]): Два сегмента в порядке их индексов.

    Fallbacks:
        Некорректная конфигурация или пустой ключ отклоняются как ValueError.
    """

    def __init__(self, shards: list[Shard] | tuple[Shard, ...]) -> None:
        """
        Проверяет и сохраняет фиксированную конфигурацию двух сегментов.

        Parameters:
            shards (list[Shard] | tuple[Shard, ...]): Сегменты в порядке
                индексов 0 и 1.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Требуются ровно два сегмента с уникальными именами и HTTP-адресами.
        """
        if len(shards) != 2:
            raise ValueError("Должно быть настроено ровно два сегмента")
        if any(not shard.name for shard in shards):
            raise ValueError("Идентификатор сегмента не должен быть пустым")
        if len({shard.name for shard in shards}) != 2:
            raise ValueError("Идентификаторы сегментов должны быть уникальными")

        normalized: list[Shard] = []
        for shard in shards:
            parsed_endpoint = urlparse(shard.endpoint)
            if (
                parsed_endpoint.scheme not in {"http", "https"}
                or not parsed_endpoint.netloc
            ):
                raise ValueError("Адрес сегмента должен быть корректным HTTP URL")
            normalized.append(Shard(shard.name, shard.endpoint.rstrip("/")))
        if len({shard.endpoint for shard in normalized}) != 2:
            raise ValueError("Адреса сегментов должны быть уникальными")
        self.shards = (normalized[0], normalized[1])

    def route(self, key: str) -> Shard:
        """
        Возвращает сегмент по целому значению SHA-256 ключа по модулю два.

        Parameters:
            key (str): Непустой строковый ключ в кодировке UTF-8.

        Returns:
            Shard: Настроенный сегмент с вычисленным индексом.

        Fallbacks:
            Пустой или нестроковый ключ отклоняется как ValueError.
        """
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise ValueError("Ключ должен быть непустой строкой")
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return self.shards[int.from_bytes(digest, byteorder="big") % 2]


class ShardedStore(IKeyValueStore):
    """
    Перенаправляет публичные операции на primary выбранного сегмента.

    Attributes:
        router (IShardRouter): Детерминированный маршрутизатор ключей.
        request_timeout (float): Тайм-аут обращения к сегменту в секундах.

    Fallbacks:
        Сетевые ошибки и некорректные ответы представлены как
        NodeUnavailableError; HTTP 404 и 500 сохраняют публичную семантику.
    """

    def __init__(
        self,
        router: IShardRouter,
        request_timeout: float = DEFAULT_SHARD_REQUEST_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Сохраняет маршрутизатор и параметры HTTP-клиента.

        Parameters:
            router (IShardRouter): Маршрутизатор двух сегментов.
            request_timeout (float): Конечный положительный тайм-аут. По
                умолчанию: 5.0.
            transport (httpx.BaseTransport | None): Транспорт для проверок. По
                умолчанию: None.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Неконечный или неположительный тайм-аут отклоняется как ValueError.
        """
        if not isfinite(request_timeout) or request_timeout <= 0:
            raise ValueError(
                "Тайм-аут сегмента должен быть конечным и положительным"
            )
        self.router = router
        self.request_timeout = request_timeout
        self._transport = transport

    def _request(
        self,
        method: str,
        shard: Shard,
        path: str,
        payload: dict[str, JsonValue] | None = None,
    ) -> httpx.Response:
        """
        Выполняет один запрос без повторения неоднозначных изменений.

        Parameters:
            method (str): HTTP-метод запроса.
            shard (Shard): Целевой сегмент.
            path (str): Путь относительно primary сегмента.
            payload (dict[str, JsonValue] | None): JSON-тело. По умолчанию:
                None.

        Returns:
            httpx.Response: Полученный ответ сегмента.

        Fallbacks:
            Ошибка соединения или тайм-аут представлены как
            NodeUnavailableError без раскрытия адреса.
        """
        try:
            with httpx.Client(
                timeout=self.request_timeout,
                transport=self._transport,
            ) as client:
                return client.request(
                    method,
                    f"{shard.endpoint}{path}",
                    json=payload,
                )
        except httpx.RequestError as error:
            raise NodeUnavailableError("Сегмент недоступен") from error

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        """
        Преобразует публичные ошибки узла в ошибки предметной области.

        Parameters:
            response (httpx.Response): Ответ primary сегмента.

        Returns:
            None: Успешный ответ не изменяется.

        Fallbacks:
            HTTP 404 становится KeyNotFoundError, HTTP 422 — ValueError,
            HTTP 500 — PersistenceError, остальные ошибки —
            NodeUnavailableError.
        """
        if response.status_code < 400:
            return
        if response.status_code == 404:
            raise KeyNotFoundError("Ключ не найден")
        if response.status_code == 422:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            raise ValueError(
                detail if isinstance(detail, str) else "Некорректный запрос"
            )
        if response.status_code == 500:
            raise PersistenceError("Ошибка постоянного хранилища сегмента")
        raise NodeUnavailableError("Сегмент недоступен")

    def put(self, key: str, value: JsonValue) -> None:
        """
        Записывает значение только в primary выбранного сегмента.

        Parameters:
            key (str): Непустой строковый ключ.
            value (JsonValue): JSON-совместимое значение.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Неоднозначный сетевой сбой не приводит к повторной записи.
        """
        shard = self.router.route(key)
        response = self._request(
            "PUT",
            shard,
            f"/kv/{quote(key, safe='')}",
            {"value": value},
        )
        self._raise_for_error(response)
        if response.status_code != status.HTTP_204_NO_CONTENT:
            raise NodeUnavailableError("Сегмент вернул некорректный ответ")

    def get(self, key: str) -> JsonValue:
        """
        Читает значение только из primary выбранного сегмента.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            JsonValue: Сохранённое JSON-совместимое значение.

        Fallbacks:
            Некорректный ответ сегмента представлен как NodeUnavailableError.
        """
        shard = self.router.route(key)
        response = self._request("GET", shard, f"/kv/{quote(key, safe='')}")
        self._raise_for_error(response)
        try:
            body = response.json()
        except ValueError as error:
            raise NodeUnavailableError(
                "Сегмент вернул некорректный ответ"
            ) from error
        if not isinstance(body, dict) or "value" not in body:
            raise NodeUnavailableError("Сегмент вернул некорректный ответ")
        return body["value"]

    def delete(self, key: str) -> None:
        """
        Удаляет значение только в primary выбранного сегмента.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Неоднозначный сетевой сбой не приводит к повторному удалению.
        """
        shard = self.router.route(key)
        response = self._request(
            "DELETE",
            shard,
            f"/kv/{quote(key, safe='')}",
        )
        self._raise_for_error(response)
        if response.status_code != status.HTTP_204_NO_CONTENT:
            raise NodeUnavailableError("Сегмент вернул некорректный ответ")

    def list_keys(self) -> list[str]:
        """
        Возвращает отсортированное объединение ключей обоих сегментов.

        Parameters:
            Не предусмотрены.

        Returns:
            list[str]: Полный список уникальных ключей.

        Fallbacks:
            Сбой любого сегмента отклоняет весь результат без частичного ответа.
        """
        keys: set[str] = set()
        for shard in self.router.shards:
            response = self._request("GET", shard, "/kv")
            self._raise_for_error(response)
            try:
                body = response.json()
            except ValueError as error:
                raise NodeUnavailableError(
                    "Сегмент вернул некорректный ответ"
                ) from error
            shard_keys = body.get("keys") if isinstance(body, dict) else None
            if not isinstance(shard_keys, list) or not all(
                isinstance(key, str) for key in shard_keys
            ):
                raise NodeUnavailableError("Сегмент вернул некорректный ответ")
            keys.update(shard_keys)
        return sorted(keys)


def get_sharded_store(request: Request) -> ShardedStore:
    """
    Возвращает единый клиент сегментов текущего приложения.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.

    Returns:
        ShardedStore: Настроенный клиент двух primary.

    Fallbacks:
        Зависимость может быть заменена через FastAPI dependency overrides.
    """
    return request.app.state.store


def get_shard_router(request: Request) -> ShardRouter:
    """
    Возвращает детерминированный маршрутизатор текущего приложения.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.

    Returns:
        ShardRouter: Настроенный маршрутизатор двух сегментов.

    Fallbacks:
        Зависимость может быть заменена через FastAPI dependency overrides.
    """
    return request.app.state.router


def create_router_app(
    shards: list[Shard] | tuple[Shard, ...] | None = None,
    *,
    request_timeout: float | None = None,
    transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    """
    Создаёт единый REST API над двумя primary сегментов.

    Parameters:
        shards (list[Shard] | tuple[Shard, ...] | None): Явная конфигурация
            сегментов. По умолчанию: None, используются переменные окружения.
        request_timeout (float | None): Тайм-аут обращения. По умолчанию: None.
        transport (httpx.BaseTransport | None): Транспорт для проверок. По
            умолчанию: None.

    Returns:
        FastAPI: Настроенное приложение маршрутизатора.

    Fallbacks:
        Неверная конфигурация прерывает создание приложения как ValueError.
    """
    configured_shards = shards if shards is not None else [
        Shard(
            os.getenv("MINIKV_SHARD_0_ID", "shard-0"),
            os.getenv("MINIKV_SHARD_0_URL", "http://shard-0-primary:8000"),
        ),
        Shard(
            os.getenv("MINIKV_SHARD_1_ID", "shard-1"),
            os.getenv("MINIKV_SHARD_1_URL", "http://shard-1-primary:8000"),
        ),
    ]
    if request_timeout is None:
        try:
            configured_timeout = float(
                os.getenv(
                    "MINIKV_SHARD_REQUEST_TIMEOUT",
                    str(DEFAULT_SHARD_REQUEST_TIMEOUT),
                )
            )
        except ValueError as error:
            raise ValueError(
                "Тайм-аут сегмента имеет неверный формат"
            ) from error
    else:
        configured_timeout = request_timeout

    router = ShardRouter(configured_shards)
    store = ShardedStore(router, configured_timeout, transport)
    application = FastAPI(
        title="MiniKV Shard Router",
        description="Единый сетевой интерфейс двух реплицируемых сегментов.",
        version="0.3.0",
    )
    application.state.router = router
    application.state.store = store

    @application.exception_handler(KeyNotFoundError)
    async def handle_missing_key(
        request: Request,
        error: KeyNotFoundError,
    ) -> JSONResponse:
        """
        Преобразует отсутствие ключа в безопасный HTTP 404.

        Parameters:
            request (Request): Текущий HTTP-запрос.
            error (KeyNotFoundError): Ошибка отсутствующего ключа.

        Returns:
            JSONResponse: Безопасный ответ HTTP 404.

        Fallbacks:
            Внутренние сведения сегмента не раскрываются.
        """
        return JSONResponse(
            status_code=404,
            content={"detail": "Ключ не найден"},
        )

    @application.exception_handler(ValueError)
    async def handle_invalid_value(
        request: Request,
        error: ValueError,
    ) -> JSONResponse:
        """
        Преобразует ошибку валидации в HTTP 422.

        Parameters:
            request (Request): Текущий HTTP-запрос.
            error (ValueError): Ошибка проверки входных данных.

        Returns:
            JSONResponse: Ответ HTTP 422.

        Fallbacks:
            Возвращается только безопасное доменное сообщение.
        """
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @application.exception_handler(PersistenceError)
    async def handle_persistence_error(
        request: Request,
        error: PersistenceError,
    ) -> JSONResponse:
        """
        Сохраняет публичную семантику ошибки постоянного хранилища.

        Parameters:
            request (Request): Текущий HTTP-запрос.
            error (PersistenceError): Ошибка primary сегмента.

        Returns:
            JSONResponse: Безопасный ответ HTTP 500.

        Fallbacks:
            Адрес и детали сегмента не раскрываются.
        """
        return JSONResponse(
            status_code=500,
            content={"detail": "Ошибка постоянного хранилища"},
        )

    @application.exception_handler(NodeUnavailableError)
    async def handle_unavailable_node(
        request: Request,
        error: NodeUnavailableError,
    ) -> JSONResponse:
        """
        Преобразует недоступность любого сегмента в HTTP 503.

        Parameters:
            request (Request): Текущий HTTP-запрос.
            error (NodeUnavailableError): Ошибка доступности сегмента.

        Returns:
            JSONResponse: Безопасный ответ HTTP 503.

        Fallbacks:
            Частичные данные и адрес недоступного узла не возвращаются.
        """
        return JSONResponse(
            status_code=503,
            content={"detail": "Хранилище недоступно"},
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        """
        Возвращает безопасный ответ для непредвиденной ошибки router.

        Parameters:
            request (Request): Текущий HTTP-запрос.
            error (Exception): Непредвиденная ошибка приложения.

        Returns:
            JSONResponse: Безопасный ответ HTTP 500.

        Fallbacks:
            Внутренние сведения и трассировка не раскрываются.
        """
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервиса"},
        )

    @application.put(
        "/kv/{key}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def put_value(
        key: str,
        payload: PutRequest,
        sharded_store: ShardedStore = Depends(get_sharded_store),
    ) -> Response:
        """
        Записывает значение через primary выбранного сегмента.

        Parameters:
            key (str): Ключ MiniKV.
            payload (PutRequest): Тело с JSON-совместимым значением.
            sharded_store (ShardedStore): Клиент сегментов.

        Returns:
            Response: Пустой ответ HTTP 204.

        Fallbacks:
            Ошибки сегмента преобразуются зарегистрированными обработчиками.
        """
        sharded_store.put(key, payload.value)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/kv/{key}", response_model=ValueResponse)
    def get_value(
        key: str,
        sharded_store: ShardedStore = Depends(get_sharded_store),
    ) -> ValueResponse:
        """
        Возвращает значение из primary выбранного сегмента.

        Parameters:
            key (str): Ключ MiniKV.
            sharded_store (ShardedStore): Клиент сегментов.

        Returns:
            ValueResponse: Ответ с сохранённым значением.

        Fallbacks:
            Отсутствующий ключ возвращает HTTP 404.
        """
        return ValueResponse(value=sharded_store.get(key))

    @application.delete(
        "/kv/{key}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def delete_value(
        key: str,
        sharded_store: ShardedStore = Depends(get_sharded_store),
    ) -> Response:
        """
        Удаляет значение через primary выбранного сегмента.

        Parameters:
            key (str): Ключ MiniKV.
            sharded_store (ShardedStore): Клиент сегментов.

        Returns:
            Response: Пустой ответ HTTP 204.

        Fallbacks:
            Отсутствующий ключ возвращает HTTP 404.
        """
        sharded_store.delete(key)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/kv", response_model=KeysResponse)
    def list_keys(
        sharded_store: ShardedStore = Depends(get_sharded_store),
    ) -> KeysResponse:
        """
        Возвращает полное отсортированное объединение ключей сегментов.

        Parameters:
            sharded_store (ShardedStore): Клиент сегментов.

        Returns:
            KeysResponse: Полный список уникальных ключей.

        Fallbacks:
            Недоступность любого сегмента возвращает HTTP 503.
        """
        return KeysResponse(keys=sharded_store.list_keys())

    @application.get("/shards/{key}", response_model=ShardResponse)
    def shard_for_key(
        key: str,
        shard_router: ShardRouter = Depends(get_shard_router),
    ) -> ShardResponse:
        """
        Возвращает только идентификатор сегмента для ключа.

        Parameters:
            key (str): Ключ MiniKV.
            shard_router (ShardRouter): Детерминированный маршрутизатор.

        Returns:
            ShardResponse: Идентификатор выбранного сегмента.

        Fallbacks:
            Endpoint не обращается к storage-узлам.
        """
        return ShardResponse(shard=shard_router.route(key).name)

    @application.get("/health", response_model=HealthResponse)
    def health(
        sharded_store: ShardedStore = Depends(get_sharded_store),
    ) -> HealthResponse:
        """
        Проверяет доступность обоих primary без частичного успеха.

        Parameters:
            sharded_store (ShardedStore): Клиент сегментов.

        Returns:
            HealthResponse: Состояние готовности маршрутизатора.

        Fallbacks:
            Недоступность любого сегмента возвращает HTTP 503.
        """
        sharded_store.list_keys()
        return HealthResponse(status="ok")

    return application


app = create_router_app()


def main() -> None:
    """
    Запускает маршрутизатор с параметрами из переменных окружения.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Функция работает до остановки ASGI-сервера.

    Fallbacks:
        Некорректный порт отклоняется как ValueError до запуска сервера.
    """
    port_value = os.getenv("MINIKV_ROUTER_PORT", "8000")
    try:
        port = int(port_value)
    except ValueError as error:
        raise ValueError(
            "MINIKV_ROUTER_PORT должен быть целым числом"
        ) from error
    if not 1 <= port <= 65535:
        raise ValueError(
            "MINIKV_ROUTER_PORT должен быть в диапазоне от 1 до 65535"
        )
    uvicorn.run(app, host="0.0.0.0", port=port)
