"""Определяет публичный контракт хранилища ключей и значений."""

from abc import ABC, abstractmethod

from src.interfaces.storage import IStorageEngine
from src.structures import JsonValue


class IKeyValueStore(ABC):
    """
    Задаёт четыре публичные операции базы данных MiniKV.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Пустые ключи отклоняются как ValueError, отсутствующие — как
        KeyNotFoundError.
    """

    @abstractmethod
    def __init__(self, storage: IStorageEngine) -> None:
        """
        Получает физический движок через внедрение зависимости.

        Parameters:
            storage (IStorageEngine): Движок загрузки и сохранения состояния.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Не предусмотрены.
        """

    @abstractmethod
    def put(self, key: str, value: JsonValue) -> None:
        """
        Создаёт значение по ключу или заменяет существующее.

        Parameters:
            key (str): Непустой строковый ключ.
            value (JsonValue): JSON-совместимое значение.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Пустой ключ отклоняется как ValueError.
        """

    @abstractmethod
    def get(self, key: str) -> JsonValue:
        """
        Возвращает значение по ключу.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            JsonValue: Сохранённое JSON-совместимое значение.

        Fallbacks:
            Пустой ключ отклоняется как ValueError, отсутствующий ключ — как
            KeyNotFoundError.
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        Удаляет значение по ключу.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Пустой ключ отклоняется как ValueError, отсутствующий ключ — как
            KeyNotFoundError.
        """

    @abstractmethod
    def list_keys(self) -> list[str]:
        """
        Возвращает ключи в детерминированном лексикографическом порядке.

        Parameters:
            Не предусмотрены.

        Returns:
            list[str]: Новый отсортированный список ключей.

        Fallbacks:
            При отсутствии данных возвращается пустой список.
        """

