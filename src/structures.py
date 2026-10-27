"""Содержит общие структуры данных для интерфейсов MiniKV."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class MutationType(StrEnum):
    """
    Задаёт допустимые типы реплицируемых изменений.

    Attributes:
        PUT (str): Создание или замена значения.
        DELETE (str): Удаление значения.

    Fallbacks:
        Не предусмотрены.
    """

    PUT = "put"
    DELETE = "delete"


class NodeRole(StrEnum):
    """
    Задаёт роль узла в топологии репликации.

    Attributes:
        PRIMARY (str): Основной узел, принимающий изменения.
        REPLICA (str): Узел только для чтения, получающий изменения.

    Fallbacks:
        Не предусмотрены.
    """

    PRIMARY = "primary"
    REPLICA = "replica"


@dataclass(frozen=True, slots=True)
class Mutation:
    """
    Описывает упорядоченное изменение для репликации.

    Attributes:
        sequence (int): Монотонно возрастающий номер изменения.
        operation (MutationType): Тип изменения.
        key (str): Изменяемый ключ.
        value (JsonValue | None): Значение для операции записи. По умолчанию: None.

    Fallbacks:
        Не предусмотрены.
    """

    sequence: int
    operation: MutationType
    key: str
    value: JsonValue | None = None


@dataclass(frozen=True, slots=True)
class ReplicationStatus:
    """
    Описывает текущее состояние репликации узла.

    Attributes:
        role (NodeRole): Роль текущего узла.
        current_sequence (int): Последний локально применённый номер.
        primary_sequence (int | None): Известный номер основного узла.
        lag (int | None): Известное отставание от основного узла.
        healthy (bool): Признак отсутствия обнаруженной ошибки репликации.
        last_successful_sync (datetime | None): Время последнего успешного
            опроса основного узла.
        last_error (str | None): Безопасное описание последней ошибки.

    Fallbacks:
        Для основного узла неизвестные поля синхронизации равны None.
    """

    role: NodeRole
    current_sequence: int
    primary_sequence: int | None
    lag: int | None
    healthy: bool
    last_successful_sync: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class Shard:
    """
    Описывает настроенный логический сегмент базы данных.

    Attributes:
        name (str): Уникальное имя сегмента.
        endpoint (str): Адрес основного узла сегмента.

    Fallbacks:
        Не предусмотрены.
    """

    name: str
    endpoint: str
