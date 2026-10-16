"""Определяет границу физического хранения состояния MiniKV."""

from abc import ABC, abstractmethod

from src.structures import JsonValue


class IStorageEngine(ABC):
    """
    Задаёт контракт загрузки и полного атомарного сохранения состояния.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Ошибки физического хранилища преобразуются в PersistenceError.
    """

    @abstractmethod
    def load(self) -> dict[str, JsonValue]:
        """
        Загружает полное состояние базы данных.

        Parameters:
            Не предусмотрены.

        Returns:
            dict[str, JsonValue]: Копия сохранённого состояния по ключам.

        Fallbacks:
            При отсутствии состояния возвращается пустой словарь; ошибки чтения
            представляются как PersistenceError.
        """

    @abstractmethod
    def save(self, state: dict[str, JsonValue]) -> None:
        """
        Атомарно сохраняет полное состояние базы данных.

        Parameters:
            state (dict[str, JsonValue]): Полное состояние для сохранения.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Ошибки сохранения представляются как PersistenceError.
        """

