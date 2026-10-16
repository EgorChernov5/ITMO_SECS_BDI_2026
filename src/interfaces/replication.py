"""Определяет границу публикации и применения изменений репликации."""

from abc import ABC, abstractmethod

from src.structures import Mutation


class IReplicationManager(ABC):
    """
    Задаёт контракт обмена упорядоченными изменениями без привязки к транспорту.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Недоступность удалённого узла представляется как NodeUnavailableError.
    """

    @abstractmethod
    def publish(self, mutation: Mutation) -> None:
        """
        Публикует подтверждённое изменение для последующей репликации.

        Parameters:
            mutation (Mutation): Упорядоченное изменение для публикации.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Недоступность получателя представляется как NodeUnavailableError.
        """

    @abstractmethod
    def apply(self, mutations: list[Mutation]) -> None:
        """
        Применяет изменения в переданном порядке.

        Parameters:
            mutations (list[Mutation]): Последовательность изменений по
                возрастанию номера.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Ошибка применения не должна скрываться или нарушать порядок.
        """

