"""Содержит транспортные структуры REST API MiniKV."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.structures import JsonValue, MutationType, NodeRole


class PutRequest(BaseModel):
    """
    Описывает тело запроса создания или замены значения.

    Attributes:
        value (JsonValue): JSON-совместимое значение для сохранения.

    Fallbacks:
        Некорректное тело запроса отклоняется стандартной валидацией FastAPI.
    """

    model_config = ConfigDict(strict=True)

    value: JsonValue


class ValueResponse(BaseModel):
    """
    Описывает ответ с сохранённым значением.

    Attributes:
        value (JsonValue): JSON-совместимое значение запрошенного ключа.

    Fallbacks:
        Не предусмотрены.
    """

    value: JsonValue


class KeysResponse(BaseModel):
    """
    Описывает ответ со списком ключей.

    Attributes:
        keys (list[str]): Ключи в лексикографическом порядке.

    Fallbacks:
        При отсутствии данных содержит пустой список.
    """

    keys: list[str]


class HealthResponse(BaseModel):
    """
    Описывает состояние готовности HTTP-сервиса.

    Attributes:
        status (str): Текущее состояние сервиса.

    Fallbacks:
        При недоступности хранилища endpoint возвращает HTTP 503.
    """

    status: str


class ShardResponse(BaseModel):
    """
    Описывает результат детерминированного выбора сегмента.

    Attributes:
        shard (str): Уникальный идентификатор выбранного сегмента.

    Fallbacks:
        Адреса узлов и сведения о репликах в ответ не включаются.
    """

    shard: str


class MutationResponse(BaseModel):
    """
    Описывает одну операцию внутренней ленты репликации.

    Attributes:
        sequence (int): Последовательный номер операции.
        operation (MutationType): Тип изменения.
        key (str): Изменённый ключ.
        value (JsonValue | None): Значение операции put. По умолчанию: None.

    Fallbacks:
        Поле value отсутствует в сериализованной операции delete.
    """

    sequence: int
    operation: MutationType
    key: str
    value: JsonValue | None = None


class OperationsResponse(BaseModel):
    """
    Описывает ограниченную пачку операций основного узла.

    Attributes:
        primary_sequence (int): Последний номер основного узла.
        operations (list[MutationResponse]): Операции после курсора.

    Fallbacks:
        При отсутствии новых операций список пуст.
    """

    primary_sequence: int
    operations: list[MutationResponse]


class ReplicationStatusResponse(BaseModel):
    """
    Описывает публичный диагностический статус репликации.

    Attributes:
        role (NodeRole): Роль текущего узла.
        current_sequence (int): Последний локальный номер.
        primary_sequence (int | None): Последний известный номер primary.
        lag (int | None): Известное отставание.
        healthy (bool): Признак отсутствия ошибки.
        last_successful_sync (datetime | None): Время успешной синхронизации.
        last_error (str | None): Безопасное описание последней ошибки.

    Fallbacks:
        Неизвестные значения представлены как None.
    """

    role: NodeRole
    current_sequence: int
    primary_sequence: int | None
    lag: int | None
    healthy: bool
    last_successful_sync: datetime | None
    last_error: str | None
