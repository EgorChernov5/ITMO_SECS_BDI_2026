"""Предоставляет REST API над реплицируемым хранилищем MiniKV."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse

from src.api.structures import (
    HealthResponse,
    KeysResponse,
    MutationResponse,
    OperationsResponse,
    PutRequest,
    ReplicationStatusResponse,
    ValueResponse,
)
from src.constants import (
    DEFAULT_DATA_FILE,
    DEFAULT_REPLICATION_BATCH_SIZE,
    DEFAULT_REPLICATION_POLL_INTERVAL,
    DEFAULT_REPLICATION_REQUEST_TIMEOUT,
)
from src.errors import (
    KeyNotFoundError,
    NodeUnavailableError,
    PersistenceError,
    ReplicationError,
)
from src.interfaces import IKeyValueStore
from src.replication import ReplicationManager
from src.storage import JsonStorage
from src.store import KeyValueStore
from src.structures import NodeRole


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


def get_replication_manager(request: Request) -> ReplicationManager:
    """
    Возвращает менеджер репликации текущего приложения.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.

    Returns:
        ReplicationManager: Настроенный менеджер текущего узла.

    Fallbacks:
        Зависимость может быть заменена через FastAPI dependency overrides.
    """
    return request.app.state.replication_manager


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


async def handle_replication_error(
    request: Request,
    error: ReplicationError,
) -> JSONResponse:
    """
    Скрывает детали нарушения репликации за HTTP 503.

    Parameters:
        request (Request): Текущий HTTP-запрос FastAPI.
        error (ReplicationError): Ошибка порядка или синхронизации.

    Returns:
        JSONResponse: Ответ с кодом HTTP 503.

    Fallbacks:
        Внутренние номера и адреса не раскрываются клиенту.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "Ошибка репликации"},
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


def create_app(
    data_file: str | Path | None = None,
    *,
    role: str | NodeRole | None = None,
    replication_log: str | Path | None = None,
    primary_url: str | None = None,
    polling_interval: float | None = None,
    batch_size: int | None = None,
    request_timeout: float | None = None,
) -> FastAPI:
    """
    Создаёт REST-приложение с постоянным состоянием и репликацией.

    Parameters:
        data_file (str | Path | None): Путь к JSON-файлу базы. По умолчанию:
            None, при котором используется MINIKV_DATA_FILE.
        role (str | NodeRole | None): Роль узла. По умолчанию: None.
        replication_log (str | Path | None): Путь к журналу. По умолчанию:
            None.
        primary_url (str | None): Адрес primary для реплики. По умолчанию:
            None.
        polling_interval (float | None): Интервал опроса. По умолчанию: None.
        batch_size (int | None): Максимальный размер пачки. По умолчанию: None.
        request_timeout (float | None): Тайм-аут запроса. По умолчанию: None.

    Returns:
        FastAPI: Настроенное приложение REST API.

    Fallbacks:
        Невозможная конфигурация или повреждённое состояние прерывает создание
        приложения явной ошибкой.
    """
    configured_path = Path(
        data_file or os.getenv("MINIKV_DATA_FILE") or DEFAULT_DATA_FILE
    )
    role_value = role or os.getenv("MINIKV_NODE_ROLE", NodeRole.PRIMARY.value)
    try:
        configured_role = NodeRole(role_value)
    except ValueError as error:
        raise ValueError(
            "MINIKV_NODE_ROLE должен быть primary или replica"
        ) from error

    configured_primary_url = primary_url or os.getenv("MINIKV_PRIMARY_URL")
    configured_log = Path(
        replication_log
        or os.getenv("MINIKV_REPLICATION_LOG")
        or configured_path.with_suffix(configured_path.suffix + ".operations.jsonl")
    )
    try:
        configured_polling_interval = (
            polling_interval
            if polling_interval is not None
            else float(
                os.getenv(
                    "MINIKV_REPLICATION_POLL_INTERVAL",
                    str(DEFAULT_REPLICATION_POLL_INTERVAL),
                )
            )
        )
        configured_batch_size = (
            batch_size
            if batch_size is not None
            else int(
                os.getenv(
                    "MINIKV_REPLICATION_BATCH_SIZE",
                    str(DEFAULT_REPLICATION_BATCH_SIZE),
                )
            )
        )
        configured_request_timeout = (
            request_timeout
            if request_timeout is not None
            else float(
                os.getenv(
                    "MINIKV_REPLICATION_REQUEST_TIMEOUT",
                    str(DEFAULT_REPLICATION_REQUEST_TIMEOUT),
                )
            )
        )
    except ValueError as error:
        raise ValueError(
            "Числовые параметры репликации имеют неверный формат"
        ) from error

    if configured_polling_interval <= 0:
        raise ValueError("Интервал опроса должен быть больше нуля")
    if configured_batch_size < 1:
        raise ValueError("Размер пачки должен быть положительным")
    if configured_request_timeout <= 0:
        raise ValueError("Тайм-аут репликации должен быть больше нуля")
    if configured_path.absolute() == configured_log.absolute():
        raise ValueError("Файл данных и журнал репликации должны различаться")
    if configured_role is NodeRole.REPLICA:
        parsed_primary_url = urlparse(configured_primary_url or "")
        if (
            parsed_primary_url.scheme not in {"http", "https"}
            or not parsed_primary_url.netloc
        ):
            raise ValueError(
                "Для replica требуется корректный MINIKV_PRIMARY_URL"
            )
    elif configured_primary_url is not None:
        raise ValueError("Primary не должен содержать MINIKV_PRIMARY_URL")

    store = KeyValueStore(JsonStorage(configured_path))
    manager = ReplicationManager(
        store=store,
        role=configured_role,
        log_path=configured_log,
        primary_url=configured_primary_url,
        polling_interval=configured_polling_interval,
        batch_size=configured_batch_size,
        request_timeout=configured_request_timeout,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """
        Запускает и останавливает фоновую задачу репликации.

        Parameters:
            application (FastAPI): Текущее приложение.

        Returns:
            AsyncIterator[None]: Управляющий итератор жизненного цикла.

        Fallbacks:
            Основной узел не создаёт фоновую задачу.
        """
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()

    application = FastAPI(
        title="MiniKV API",
        description="Сетевой интерфейс учебной базы ключей и JSON-значений.",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.store = store
    application.state.replication_manager = manager

    application.add_exception_handler(KeyNotFoundError, handle_missing_key)
    application.add_exception_handler(ValueError, handle_invalid_value)
    application.add_exception_handler(PersistenceError, handle_persistence_error)
    application.add_exception_handler(
        NodeUnavailableError,
        handle_unavailable_node,
    )
    application.add_exception_handler(
        ReplicationError,
        handle_replication_error,
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
        replication: ReplicationManager = Depends(get_replication_manager),
    ) -> Response:
        """
        Создаёт значение на основном узле или отклоняет запись на реплике.

        Parameters:
            key (str): Ключ MiniKV из пути запроса.
            payload (PutRequest): Тело с JSON-совместимым значением.
            replication (ReplicationManager): Менеджер текущего узла.

        Returns:
            Response: Пустой ответ с кодом HTTP 204.

        Fallbacks:
            Реплика возвращает HTTP 403 без изменения состояния.
        """
        if replication.role is NodeRole.REPLICA:
            raise HTTPException(
                status_code=403,
                detail="Реплика доступна только для чтения",
            )
        replication.put(key, payload.value)
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
        replication: ReplicationManager = Depends(get_replication_manager),
    ) -> Response:
        """
        Удаляет значение на основном узле или отклоняет запрос реплики.

        Parameters:
            key (str): Ключ MiniKV из пути запроса.
            replication (ReplicationManager): Менеджер текущего узла.

        Returns:
            Response: Пустой ответ с кодом HTTP 204.

        Fallbacks:
            Реплика возвращает HTTP 403 без изменения состояния.
        """
        if replication.role is NodeRole.REPLICA:
            raise HTTPException(
                status_code=403,
                detail="Реплика доступна только для чтения",
            )
        replication.delete(key)
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
        Проверяет доступность локального хранилища.

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

    @application.get(
        "/replication/operations",
        response_model=OperationsResponse,
        response_model_exclude_none=True,
    )
    def replication_operations(
        after: int = Query(ge=0),
        replication: ReplicationManager = Depends(get_replication_manager),
    ) -> OperationsResponse:
        """
        Возвращает следующую пачку упорядоченных операций primary.

        Parameters:
            after (int): Последний известный номер операции.
            replication (ReplicationManager): Менеджер текущего узла.

        Returns:
            OperationsResponse: Номер primary и следующая пачка.

        Fallbacks:
            Реплика возвращает HTTP 403, неверный курсор — HTTP 422.
        """
        if replication.role is NodeRole.REPLICA:
            raise HTTPException(
                status_code=403,
                detail="Лента операций доступна только на primary",
            )
        operations = [
            MutationResponse(**replication.record(mutation))
            for mutation in replication.operations_after(after)
        ]
        return OperationsResponse(
            primary_sequence=replication.current_sequence,
            operations=operations,
        )

    @application.get(
        "/replication/status",
        response_model=ReplicationStatusResponse,
    )
    def replication_status(
        replication: ReplicationManager = Depends(get_replication_manager),
    ) -> ReplicationStatusResponse:
        """
        Возвращает роль, номера и безопасное состояние синхронизации.

        Parameters:
            replication (ReplicationManager): Менеджер текущего узла.

        Returns:
            ReplicationStatusResponse: Диагностический статус репликации.

        Fallbacks:
            Неизвестные номера и время представлены как null.
        """
        current_status = replication.status()
        return ReplicationStatusResponse(
            role=current_status.role,
            current_sequence=current_status.current_sequence,
            primary_sequence=current_status.primary_sequence,
            lag=current_status.lag,
            healthy=current_status.healthy,
            last_successful_sync=current_status.last_successful_sync,
            last_error=current_status.last_error,
        )

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
