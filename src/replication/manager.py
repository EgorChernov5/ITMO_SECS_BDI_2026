"""Реализует журнал и фоновую синхронизацию primary-replica."""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

import httpx

from src.errors import KeyNotFoundError, PersistenceError, ReplicationError
from src.interfaces import IKeyValueStore, IReplicationManager
from src.structures import (
    JsonValue,
    Mutation,
    MutationType,
    NodeRole,
    ReplicationStatus,
)


class ReplicationManager(IReplicationManager):
    """
    Управляет упорядоченным журналом и синхронизацией одного узла.

    Attributes:
        store (IKeyValueStore): Локальное хранилище узла.
        role (NodeRole): Роль узла в топологии.
        log_path (Path): Путь к локальному журналу операций.
        primary_url (str | None): Адрес основного узла.
        polling_interval (float): Интервал опроса в секундах.
        batch_size (int): Максимальный размер возвращаемой пачки.
        request_timeout (float): Тайм-аут HTTP-запроса в секундах.

    Fallbacks:
        Ошибки журнала представляются как PersistenceError, нарушения порядка
        — как ReplicationError, а недоступность основного узла сохраняется в
        статусе и приводит к повторному опросу.
    """

    def __init__(
        self,
        store: IKeyValueStore,
        role: NodeRole,
        log_path: str | Path,
        primary_url: str | None = None,
        polling_interval: float = 1.0,
        batch_size: int = 100,
        request_timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Загружает и проверяет локальный журнал репликации.

        Parameters:
            store (IKeyValueStore): Локальное хранилище узла.
            role (NodeRole): Роль узла в топологии.
            log_path (str | Path): Путь к журналу JSON Lines.
            primary_url (str | None): Адрес основного узла. По умолчанию: None.
            polling_interval (float): Интервал опроса. По умолчанию: 1.0.
            batch_size (int): Размер пачки. По умолчанию: 100.
            request_timeout (float): Тайм-аут запроса. По умолчанию: 5.0.
            transport (httpx.AsyncBaseTransport | None): Транспорт HTTP для
                проверок. По умолчанию: None.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Повреждённый или неупорядоченный журнал вызывает PersistenceError.
        """
        self.store = store
        self.role = role
        self.log_path = Path(log_path)
        self.primary_url = primary_url.rstrip("/") if primary_url else None
        self.polling_interval = polling_interval
        self.batch_size = batch_size
        self.request_timeout = request_timeout
        self._transport = transport
        self._lock = Lock()
        self._mutations = self._load_log()
        self._primary_sequence = (
            len(self._mutations) if role is NodeRole.PRIMARY else None
        )
        self._last_successful_sync: datetime | None = None
        self._last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def current_sequence(self) -> int:
        """
        Возвращает последний номер локального журнала.

        Parameters:
            Не предусмотрены.

        Returns:
            int: Последний применённый номер или ноль для пустого журнала.

        Fallbacks:
            Для пустого журнала возвращается 0.
        """
        return len(self._mutations)

    def _load_log(self) -> list[Mutation]:
        """
        Загружает журнал и проверяет непрерывность последовательности.

        Parameters:
            Не предусмотрены.

        Returns:
            list[Mutation]: Проверенные операции в исходном порядке.

        Fallbacks:
            Отсутствующий файл означает пустой журнал; остальные ошибки
            представляются как PersistenceError.
        """
        try:
            with self.log_path.open(encoding="utf-8") as file:
                lines = list(file)
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as error:
            raise PersistenceError(
                "Не удалось загрузить журнал репликации"
            ) from error

        mutations: list[Mutation] = []
        try:
            for expected_sequence, line in enumerate(lines, start=1):
                mutation = self._parse_record(json.loads(line))
                if mutation.sequence != expected_sequence:
                    raise ValueError("Нарушена последовательность журнала")
                mutations.append(mutation)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise PersistenceError("Журнал репликации повреждён") from error
        return mutations

    @staticmethod
    def _parse_record(record: object) -> Mutation:
        """
        Преобразует одну JSON-запись в проверенную операцию.

        Parameters:
            record (object): Декодированная запись журнала.

        Returns:
            Mutation: Проверенная операция репликации.

        Fallbacks:
            Некорректная структура вызывает ValueError.
        """
        if not isinstance(record, dict):
            raise ValueError("Запись журнала должна быть объектом")
        sequence = record.get("sequence")
        key = record.get("key")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError("Номер операции должен быть целым числом")
        if sequence < 1 or not isinstance(key, str) or not key:
            raise ValueError("Запись журнала содержит неверные поля")
        operation = MutationType(record.get("operation"))
        if operation is MutationType.PUT:
            if "value" not in record:
                raise ValueError("Операция put должна содержать значение")
            value = record["value"]
        else:
            if "value" in record:
                raise ValueError("Операция delete не должна содержать значение")
            value = None
        return Mutation(sequence, operation, key, value)

    @staticmethod
    def record(mutation: Mutation) -> dict[str, JsonValue]:
        """
        Создаёт JSON-совместимую запись операции.

        Parameters:
            mutation (Mutation): Операция репликации.

        Returns:
            dict[str, JsonValue]: Запись для журнала и HTTP-ответа.

        Fallbacks:
            Для delete поле value не создаётся.
        """
        record: dict[str, JsonValue] = {
            "sequence": mutation.sequence,
            "operation": mutation.operation.value,
            "key": mutation.key,
        }
        if mutation.operation is MutationType.PUT:
            record["value"] = mutation.value
        return record

    def _append(self, mutation: Mutation) -> None:
        """
        Надёжно добавляет одну операцию в конец журнала.

        Parameters:
            mutation (Mutation): Следующая последовательная операция.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Ошибки сериализации и файловой системы вызывают PersistenceError.
        """
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", newline="\n") as file:
                json.dump(
                    self.record(mutation),
                    file,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
        except (OSError, TypeError, ValueError) as error:
            raise PersistenceError(
                "Не удалось сохранить журнал репликации"
            ) from error
        self._mutations.append(mutation)

    def publish(self, mutation: Mutation) -> None:
        """
        Публикует следующую операцию в журнале основного узла.

        Parameters:
            mutation (Mutation): Следующая упорядоченная операция.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Вызов на реплике или неверный номер вызывает ReplicationError.
        """
        with self._lock:
            if self.role is not NodeRole.PRIMARY:
                raise ReplicationError("Реплика не публикует операции")
            if mutation.sequence != self.current_sequence + 1:
                raise ReplicationError("Нарушен порядок публикации")
            self._append(mutation)
            self._primary_sequence = mutation.sequence

    def put(self, key: str, value: JsonValue) -> None:
        """
        Сохраняет значение и добавляет подтверждённую операцию в журнал.

        Parameters:
            key (str): Изменяемый ключ.
            value (JsonValue): Новое JSON-значение.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Реплика отклоняет вызов; ошибка журнала не возвращается как успех.
        """
        with self._lock:
            if self.role is not NodeRole.PRIMARY:
                raise ReplicationError("Реплика доступна только для чтения")
            self.store.put(key, value)
            mutation = Mutation(
                self.current_sequence + 1,
                MutationType.PUT,
                key,
                value,
            )
            self._append(mutation)
            self._primary_sequence = mutation.sequence

    def delete(self, key: str) -> None:
        """
        Удаляет значение и добавляет подтверждённую операцию в журнал.

        Parameters:
            key (str): Удаляемый ключ.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Реплика отклоняет вызов; отсутствующий ключ сохраняет публичное
            поведение KeyNotFoundError.
        """
        with self._lock:
            if self.role is not NodeRole.PRIMARY:
                raise ReplicationError("Реплика доступна только для чтения")
            self.store.delete(key)
            mutation = Mutation(
                self.current_sequence + 1,
                MutationType.DELETE,
                key,
            )
            self._append(mutation)
            self._primary_sequence = mutation.sequence

    def apply(self, mutations: list[Mutation]) -> None:
        """
        Последовательно и идемпотентно применяет операции на реплике.

        Parameters:
            mutations (list[Mutation]): Операции в порядке возрастания номера.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Повтор совпадающей операции пропускается; конфликт или разрыв
            последовательности вызывает ReplicationError.
        """
        with self._lock:
            if self.role is not NodeRole.REPLICA:
                raise ReplicationError(
                    "Основной узел не применяет удалённый журнал"
                )
            for mutation in mutations:
                if mutation.sequence <= self.current_sequence:
                    if self._mutations[mutation.sequence - 1] != mutation:
                        raise ReplicationError(
                            "Обнаружен конфликт номера операции"
                        )
                    continue
                if mutation.sequence != self.current_sequence + 1:
                    raise ReplicationError(
                        "Обнаружен разрыв журнала репликации"
                    )

                if mutation.operation is MutationType.PUT:
                    self.store.put(mutation.key, mutation.value)
                else:
                    try:
                        self.store.delete(mutation.key)
                    except KeyNotFoundError:
                        pass
                # Номер сохраняется только после устойчивого локального изменения.
                self._append(mutation)

    def operations_after(self, sequence: int) -> list[Mutation]:
        """
        Возвращает ограниченную пачку операций строго после номера.

        Parameters:
            sequence (int): Последний известный клиенту номер.

        Returns:
            list[Mutation]: Следующая последовательная пачка операций.

        Fallbacks:
            Отрицательный или опережающий курсор вызывает ValueError.
        """
        if self.role is not NodeRole.PRIMARY:
            raise ReplicationError(
                "Лента операций доступна только на основном узле"
            )
        if sequence < 0 or sequence > self.current_sequence:
            raise ValueError("Курсор репликации находится вне журнала")
        with self._lock:
            return list(
                self._mutations[sequence : sequence + self.batch_size]
            )

    async def synchronize_once(self) -> None:
        """
        Выполняет один опрос основного узла и применяет полученную пачку.

        Parameters:
            Не предусмотрены.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Ошибка запроса или применения сохраняется в безопасном статусе и
            передаётся вызывающей стороне.
        """
        if self.role is not NodeRole.REPLICA or self.primary_url is None:
            raise ReplicationError(
                "Синхронизация доступна только настроенной реплике"
            )
        try:
            async with httpx.AsyncClient(
                timeout=self.request_timeout,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{self.primary_url}/replication/operations",
                    params={"after": self.current_sequence},
                )
                response.raise_for_status()
            payload = response.json()
            primary_sequence = payload["primary_sequence"]
            records = payload["operations"]
            if (
                isinstance(primary_sequence, bool)
                or not isinstance(primary_sequence, int)
                or primary_sequence < self.current_sequence
                or not isinstance(records, list)
            ):
                raise ReplicationError(
                    "Основной узел вернул неверное состояние"
                )
            mutations = [self._parse_record(record) for record in records]
            self.apply(mutations)
            self._primary_sequence = primary_sequence
            self._last_successful_sync = datetime.now(UTC)
            self._last_error = None
        except httpx.HTTPError as error:
            self._last_error = "Основной узел временно недоступен"
            raise ReplicationError(self._last_error) from error
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._last_error = "Основной узел вернул некорректный ответ"
            raise ReplicationError(self._last_error) from error
        except (PersistenceError, ReplicationError):
            self._last_error = "Не удалось применить операции репликации"
            raise

    async def start(self) -> None:
        """
        Запускает фоновый опрос для реплики.

        Parameters:
            Не предусмотрены.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            На основном узле метод ничего не запускает.
        """
        if self.role is NodeRole.PRIMARY or self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._poll(),
            name="minikv-replication",
        )

    async def _poll(self) -> None:
        """
        Повторяет синхронизацию до остановки приложения.

        Parameters:
            Не предусмотрены.

        Returns:
            None: Метод завершается после сигнала остановки.

        Fallbacks:
            Ошибки отдельного опроса не останавливают будущие попытки.
        """
        if self._stop_event is None:
            return
        while not self._stop_event.is_set():
            try:
                await self.synchronize_once()
            except (PersistenceError, ReplicationError):
                pass
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.polling_interval,
                )
            except TimeoutError:
                pass

    async def stop(self) -> None:
        """
        Останавливает фоновый опрос и ожидает завершения задачи.

        Parameters:
            Не предусмотрены.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Если задача не запускалась, метод ничего не делает.
        """
        if self._task is None or self._stop_event is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        self._stop_event = None

    def status(self) -> ReplicationStatus:
        """
        Возвращает безопасный снимок состояния репликации.

        Parameters:
            Не предусмотрены.

        Returns:
            ReplicationStatus: Текущая роль, номера и состояние синхронизации.

        Fallbacks:
            Неизвестное отставание реплики представляется как None.
        """
        primary_sequence = self._primary_sequence
        lag = (
            None
            if primary_sequence is None
            else max(primary_sequence - self.current_sequence, 0)
        )
        return ReplicationStatus(
            role=self.role,
            current_sequence=self.current_sequence,
            primary_sequence=primary_sequence,
            lag=lag,
            healthy=self._last_error is None,
            last_successful_sync=self._last_successful_sync,
            last_error=self._last_error,
        )
