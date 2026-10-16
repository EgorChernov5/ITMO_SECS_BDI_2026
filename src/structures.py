"""Содержит общие структуры данных для интерфейсов MiniKV."""

from dataclasses import dataclass
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
