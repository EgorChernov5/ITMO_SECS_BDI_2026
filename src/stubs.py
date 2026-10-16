"""Содержит явные нерабочие заглушки архитектурных компонентов MiniKV."""

from src.constants import MIN_KEY_LENGTH
from src.interfaces import (
    IKeyValueStore,
    IReplicationManager,
    IShardRouter,
    IStorageEngine,
)
from src.structures import JsonValue, Mutation, Shard


class StorageEngineStub(IStorageEngine):
    """
    Представляет неработающую заглушку физического хранилища.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Каждый вызов завершается NotImplementedError.
    """

    def load(self) -> dict[str, JsonValue]:
        """
        Отклоняет загрузку до реализации лабораторной работы № 2.

        Parameters:
            Не предусмотрены.

        Returns:
            dict[str, JsonValue]: Метод не возвращает состояние.

        Fallbacks:
            Всегда возбуждает NotImplementedError.
        """
        raise NotImplementedError(
            "Хранилище будет реализовано в лабораторной работе № 2"
        )

    def save(self, state: dict[str, JsonValue]) -> None:
        """
        Отклоняет сохранение до реализации лабораторной работы № 2.

        Parameters:
            state (dict[str, JsonValue]): Состояние, которое не будет сохранено.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Всегда возбуждает NotImplementedError.
        """
        raise NotImplementedError(
            "Хранилище будет реализовано в лабораторной работе № 2"
        )


class KeyValueStoreStub(IKeyValueStore):
    """
    Показывает зависимость публичного хранилища от физического движка.

    Attributes:
        storage (IStorageEngine): Физический движок, переданный через конструктор.

    Fallbacks:
        Корректные вызовы завершаются NotImplementedError.
    """

    def __init__(self, storage: IStorageEngine) -> None:
        """
        Сохраняет зависимость от физического движка.

        Parameters:
            storage (IStorageEngine): Физический движок будущей реализации.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Не предусмотрены.
        """
        self.storage = storage

    def put(self, key: str, value: JsonValue) -> None:
        """
        Проверяет ключ и отклоняет запись как нереализованную.

        Parameters:
            key (str): Непустой строковый ключ.
            value (JsonValue): JSON-совместимое значение.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Пустой ключ отклоняется как ValueError, иначе возбуждается
            NotImplementedError.
        """
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise ValueError("Ключ должен быть непустой строкой")
        raise NotImplementedError(
            "Операции будут реализованы в лабораторной работе № 2"
        )

    def get(self, key: str) -> JsonValue:
        """
        Проверяет ключ и отклоняет чтение как нереализованное.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            JsonValue: Метод не возвращает значение.

        Fallbacks:
            Пустой ключ отклоняется как ValueError, иначе возбуждается
            NotImplementedError.
        """
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise ValueError("Ключ должен быть непустой строкой")
        raise NotImplementedError(
            "Операции будут реализованы в лабораторной работе № 2"
        )

    def delete(self, key: str) -> None:
        """
        Проверяет ключ и отклоняет удаление как нереализованное.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Пустой ключ отклоняется как ValueError, иначе возбуждается
            NotImplementedError.
        """
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise ValueError("Ключ должен быть непустой строкой")
        raise NotImplementedError(
            "Операции будут реализованы в лабораторной работе № 2"
        )

    def list_keys(self) -> list[str]:
        """
        Отклоняет перечисление ключей как нереализованное.

        Parameters:
            Не предусмотрены.

        Returns:
            list[str]: Метод не возвращает список.

        Fallbacks:
            Всегда возбуждает NotImplementedError.
        """
        raise NotImplementedError(
            "Операции будут реализованы в лабораторной работе № 2"
        )


class ReplicationManagerStub(IReplicationManager):
    """
    Представляет неработающую заглушку репликации.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Каждый вызов завершается NotImplementedError.
    """

    def publish(self, mutation: Mutation) -> None:
        """
        Отклоняет публикацию до лабораторной работы № 4.

        Parameters:
            mutation (Mutation): Изменение, которое не будет опубликовано.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Всегда возбуждает NotImplementedError.
        """
        raise NotImplementedError(
            "Репликация будет реализована в лабораторной работе № 4"
        )

    def apply(self, mutations: list[Mutation]) -> None:
        """
        Отклоняет применение до лабораторной работы № 4.

        Parameters:
            mutations (list[Mutation]): Изменения, которые не будут применены.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Всегда возбуждает NotImplementedError.
        """
        raise NotImplementedError(
            "Репликация будет реализована в лабораторной работе № 4"
        )


class ShardRouterStub(IShardRouter):
    """
    Представляет неработающую заглушку маршрутизации по сегментам.

    Attributes:
        shards (tuple[Shard, ...]): Настроенные сегменты будущей реализации.

    Fallbacks:
        Корректный вызов завершается NotImplementedError.
    """

    def __init__(self, shards: tuple[Shard, ...]) -> None:
        """
        Сохраняет конфигурацию сегментов без выбора алгоритма.

        Parameters:
            shards (tuple[Shard, ...]): Настроенные сегменты.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Не предусмотрены.
        """
        self.shards = shards

    def route(self, key: str) -> Shard:
        """
        Проверяет ключ и отклоняет маршрутизацию как нереализованную.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            Shard: Метод не возвращает сегмент.

        Fallbacks:
            Пустой ключ отклоняется как ValueError, иначе возбуждается
            NotImplementedError.
        """
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise ValueError("Ключ должен быть непустой строкой")
        raise NotImplementedError(
            "Шардинг будет реализован в лабораторной работе № 5"
        )
