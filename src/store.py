"""Реализует локальное хранилище ключей и JSON-значений MiniKV."""

from copy import deepcopy
from math import isfinite

from src.constants import MIN_KEY_LENGTH
from src.errors import KeyNotFoundError, PersistenceError
from src.interfaces import IKeyValueStore, IStorageEngine
from src.structures import JsonValue


class KeyValueStore(IKeyValueStore):
    """
    Управляет состоянием MiniKV и сохраняет каждое успешное изменение.

    Attributes:
        storage (IStorageEngine): Физический движок состояния.

    Fallbacks:
        Некорректные ключи и значения отклоняются как ValueError, отсутствующие
        ключи — как KeyNotFoundError, ошибки движка передаются как
        PersistenceError.
    """

    def __init__(self, storage: IStorageEngine) -> None:
        """
        Загружает и проверяет состояние из физического движка.

        Parameters:
            storage (IStorageEngine): Движок загрузки и сохранения состояния.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Некорректное сохранённое состояние представляется как
            PersistenceError.
        """
        self.storage = storage
        state = storage.load()
        try:
            for key, value in state.items():
                self._validate_key(key)
                self._validate_value(value)
        except ValueError as error:
            raise PersistenceError(
                "Сохранённое состояние MiniKV некорректно"
            ) from error
        self._state = deepcopy(state)

    @staticmethod
    def _validate_key(key: str) -> None:
        """
        Проверяет публичный ключ MiniKV.

        Parameters:
            key (str): Проверяемый ключ.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Непустой строкой считается только ключ требуемой длины; остальные
            значения отклоняются как ValueError.
        """
        if not isinstance(key, str) or len(key) < MIN_KEY_LENGTH:
            raise ValueError("Ключ должен быть непустой строкой")

    @classmethod
    def _validate_value(
        cls,
        value: object,
        active_containers: set[int] | None = None,
    ) -> None:
        """
        Проверяет соответствие значения строгой модели JSON.

        Parameters:
            value (object): Проверяемое значение.
            active_containers (set[int] | None): Идентификаторы контейнеров в
                текущей ветви обхода. По умолчанию: None.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Неподдерживаемые типы, нестроковые ключи объектов, нечисловые
            значения float и циклические контейнеры отклоняются как ValueError.
        """
        if value is None or isinstance(value, (str, bool, int)):
            return
        if isinstance(value, float):
            if isfinite(value):
                return
            raise ValueError("Число JSON должно быть конечным")
        if not isinstance(value, (list, dict)):
            raise ValueError("Значение должно быть совместимо с JSON")

        containers = active_containers if active_containers is not None else set()
        container_id = id(value)
        if container_id in containers:
            raise ValueError("Значение JSON не должно содержать циклы")
        containers.add(container_id)
        try:
            if isinstance(value, list):
                for item in value:
                    cls._validate_value(item, containers)
            else:
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError("Ключи объектов JSON должны быть строками")
                    cls._validate_value(item, containers)
        finally:
            containers.remove(container_id)

    def put(self, key: str, value: JsonValue) -> None:
        """
        Создаёт значение по ключу или заменяет существующее.

        Parameters:
            key (str): Непустой строковый ключ.
            value (JsonValue): JSON-совместимое значение.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Некорректные ключ и значение отклоняются как ValueError; при ошибке
            сохранения прежнее состояние остаётся активным.
        """
        self._validate_key(key)
        self._validate_value(value)
        new_state = deepcopy(self._state)
        new_state[key] = deepcopy(value)
        self.storage.save(new_state)
        self._state = new_state

    def get(self, key: str) -> JsonValue:
        """
        Возвращает независимую копию значения по ключу.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            JsonValue: Копия сохранённого JSON-совместимого значения.

        Fallbacks:
            Некорректный ключ отклоняется как ValueError, отсутствующий ключ —
            как KeyNotFoundError.
        """
        self._validate_key(key)
        try:
            return deepcopy(self._state[key])
        except KeyError as error:
            raise KeyNotFoundError(f"Ключ не найден: {key}") from error

    def delete(self, key: str) -> None:
        """
        Удаляет значение по ключу и сохраняет новое состояние.

        Parameters:
            key (str): Непустой строковый ключ.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Некорректный ключ отклоняется как ValueError, отсутствующий ключ —
            как KeyNotFoundError; при ошибке сохранения прежнее состояние
            остаётся активным.
        """
        self._validate_key(key)
        if key not in self._state:
            raise KeyNotFoundError(f"Ключ не найден: {key}")
        new_state = deepcopy(self._state)
        del new_state[key]
        self.storage.save(new_state)
        self._state = new_state

    def list_keys(self) -> list[str]:
        """
        Возвращает новый список ключей в лексикографическом порядке.

        Parameters:
            Не предусмотрены.

        Returns:
            list[str]: Отсортированный список ключей.

        Fallbacks:
            При отсутствии данных возвращается пустой список.
        """
        return sorted(self._state)
