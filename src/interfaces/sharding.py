"""Определяет границу выбора сегмента по ключу."""

from abc import ABC, abstractmethod

from src.structures import Shard


class IShardRouter(ABC):
    """
    Задаёт контракт отображения ключа на настроенный сегмент.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Пустой ключ отклоняется как ValueError, недоступный сегмент — как
        NodeUnavailableError.
    """

    @abstractmethod
    def route(self, key: str) -> Shard:
        """
        Выбирает настроенный сегмент для ключа.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            Shard: Настроенный сегмент для выполнения операции.

        Fallbacks:
            Пустой ключ отклоняется как ValueError; отсутствие доступного
            сегмента представляется как NodeUnavailableError.
        """
