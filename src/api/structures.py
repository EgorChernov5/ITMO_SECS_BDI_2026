"""Содержит транспортные структуры REST API MiniKV."""

from pydantic import BaseModel, ConfigDict

from src.structures import JsonValue


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
