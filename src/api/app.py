"""Предоставляет REST API над одним экземпляром хранилища MiniKV."""

import os
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from src.api.structures import (
    HealthResponse,
    KeysResponse,
    PutRequest,
    ValueResponse,
)
from src.errors import (
    KeyNotFoundError,
    NodeUnavailableError,
    PersistenceError,
)
from src.interfaces import IKeyValueStore
from src.storage import JsonStorage
from src.store import KeyValueStore

DEFAULT_DATA_FILE = Path("data/data.json")


def get_store(request: Request) -> IKeyValueStore:
    """
    Возвращает единый экземпляр хранилища текущего приложения.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.

    Returns:
        IKeyValueStore: Настроенное хранилище MiniKV.

    Fallbacks:
        Зависимость может быть заменена через FastAPI dependency overrides.
    """
    return request.app.state.store


async def handle_missing_key(
    request: Request,
    error: KeyNotFoundError,
) -> JSONResponse:
    """
    Преобразует отсутствие ключа в безопасный HTTP-ответ.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.
        error (KeyNotFoundError): Ошибка предметной области.

    Returns:
        JSONResponse: Ответ с кодом HTTP 404.

    Fallbacks:
        Текст исходной ошибки не включается в ответ.
    """
    return JSONResponse(status_code=404, content={"detail": "Ключ не найден"})


async def handle_invalid_value(
    request: Request,
    error: ValueError,
) -> JSONResponse:
    """
    Преобразует ошибку доменной валидации в HTTP 422.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.
        error (ValueError): Ошибка проверки ключа или значения.

    Returns:
        JSONResponse: Ответ с кодом HTTP 422.

    Fallbacks:
        Возвращает безопасное сообщение доменной валидации.
    """
    return JSONResponse(status_code=422, content={"detail": str(error)})


async def handle_persistence_error(
    request: Request,
    error: PersistenceError,
) -> JSONResponse:
    """
    Скрывает детали сбоя постоянного хранилища за HTTP 500.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.
        error (PersistenceError): Ошибка чтения или сохранения данных.

    Returns:
        JSONResponse: Ответ с кодом HTTP 500.

    Fallbacks:
        Путь к файлу и исходное исключение не раскрываются клиенту.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Ошибка постоянного хранилища"},
    )


async def handle_unavailable_node(
    request: Request,
    error: NodeUnavailableError,
) -> JSONResponse:
    """
    Преобразует недоступность хранилища в HTTP 503.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.
        error (NodeUnavailableError): Ошибка доступности узла.

    Returns:
        JSONResponse: Ответ с кодом HTTP 503.

    Fallbacks:
        Внутренние сведения об узле не раскрываются клиенту.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "Хранилище недоступно"},
    )


async def handle_unexpected_error(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """
    Возвращает безопасный ответ для непредвиденной ошибки.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.
        error (Exception): Непредвиденное исключение приложения.

    Returns:
        JSONResponse: Ответ с кодом HTTP 500 без внутренних деталей.

    Fallbacks:
        Трассировка, пути и другие внутренние данные не включаются в ответ.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервиса"},
    )


def create_app(data_file: str | Path | None = None) -> FastAPI:
    """
    Создаёт REST-приложение с одним постоянным экземпляром MiniKV.

    Parameters:
        data_file (str | Path | None): Путь к JSON-файлу базы. По умолчанию:
            None, при котором используется MINIKV_DATA_FILE или
            data/data.json.

    Returns:
        FastAPI: Настроенное приложение REST API.

    Fallbacks:
        Ошибка первоначальной загрузки состояния прерывает создание
        приложения; зависимости endpoint можно заменить в тестах.
    """
    configured_path = data_file or os.getenv("MINIKV_DATA_FILE") or DEFAULT_DATA_FILE
    application = FastAPI(
        title="MiniKV API",
        description="Сетевой интерфейс учебной базы ключей и JSON-значений.",
        version="0.1.0",
    )
    application.state.store = KeyValueStore(JsonStorage(configured_path))

    application.add_exception_handler(KeyNotFoundError, handle_missing_key)
    application.add_exception_handler(ValueError, handle_invalid_value)
    application.add_exception_handler(PersistenceError, handle_persistence_error)
    application.add_exception_handler(
        NodeUnavailableError,
        handle_unavailable_node,
    )
    application.add_exception_handler(Exception, handle_unexpected_error)

    @application.put(
        "/kv/{key}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def put_value(
        key: str,
        payload: PutRequest,
        store: IKeyValueStore = Depends(get_store),
    ) -> Response:
        """
        Создаёт значение по ключу или заменяет существующее.

        Parameters:
            key (str): Ключ MiniKV из пути запроса.
            payload (PutRequest): Тело с JSON-совместимым значением.
            store (IKeyValueStore): Хранилище приложения.

        Returns:
            Response: Пустой ответ с кодом HTTP 204.

        Fallbacks:
            Некорректные данные преобразуются в HTTP 422, сбой сохранения —
            в HTTP 500.
        """
        store.put(key, payload.value)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/kv/{key}", response_model=ValueResponse)
    def get_value(
        key: str,
        store: IKeyValueStore = Depends(get_store),
    ) -> ValueResponse:
        """
        Возвращает значение указанного ключа.

        Parameters:
            key (str): Ключ MiniKV из пути запроса.
            store (IKeyValueStore): Хранилище приложения.

        Returns:
            ValueResponse: Ответ с сохранённым JSON-значением.

        Fallbacks:
            Отсутствующий ключ преобразуется в HTTP 404.
        """
        return ValueResponse(value=store.get(key))

    @application.delete(
        "/kv/{key}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def delete_value(
        key: str,
        store: IKeyValueStore = Depends(get_store),
    ) -> Response:
        """
        Удаляет значение указанного ключа.

        Parameters:
            key (str): Ключ MiniKV из пути запроса.
            store (IKeyValueStore): Хранилище приложения.

        Returns:
            Response: Пустой ответ с кодом HTTP 204.

        Fallbacks:
            Отсутствующий ключ преобразуется в HTTP 404, сбой сохранения —
            в HTTP 500.
        """
        store.delete(key)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/kv", response_model=KeysResponse)
    def list_keys(
        store: IKeyValueStore = Depends(get_store),
    ) -> KeysResponse:
        """
        Возвращает отсортированные ключи базы данных.

        Parameters:
            store (IKeyValueStore): Хранилище приложения.

        Returns:
            KeysResponse: Ответ со списком ключей.

        Fallbacks:
            Ошибка хранилища преобразуется в HTTP 500.
        """
        return KeysResponse(keys=store.list_keys())

    @application.get("/health", response_model=HealthResponse)
    def health(
        store: IKeyValueStore = Depends(get_store),
    ) -> HealthResponse:
        """
        Проверяет доступность экземпляра хранилища.

        Parameters:
            store (IKeyValueStore): Хранилище приложения.

        Returns:
            HealthResponse: Состояние готовности сервиса.

        Fallbacks:
            Ошибка хранилища преобразуется в HTTP 503.
        """
        try:
            store.list_keys()
        except PersistenceError as error:
            raise NodeUnavailableError("Хранилище недоступно") from error
        return HealthResponse(status="ok")

    return application


app = create_app()


def main() -> None:
    """
    Запускает HTTP-сервис с параметрами из переменных окружения.

    Parameters:
        Не предусмотрены.

    Returns:
        None: Функция работает до остановки ASGI-сервера.

    Fallbacks:
        Некорректный MINIKV_PORT отклоняется как ValueError до запуска сервера.
    """
    port_value = os.getenv("MINIKV_PORT", "8000")
    try:
        port = int(port_value)
    except ValueError as error:
        raise ValueError("MINIKV_PORT должен быть целым числом") from error
    if not 1 <= port <= 65535:
        raise ValueError("MINIKV_PORT должен быть в диапазоне от 1 до 65535")

    uvicorn.run(app, host="0.0.0.0", port=port)

