"""Реализует атомарное хранение состояния MiniKV в JSON-файле."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.errors import PersistenceError
from src.interfaces import IStorageEngine
from src.structures import JsonValue


class JsonStorage(IStorageEngine):
    """
    Хранит полное состояние MiniKV в одном JSON-файле.

    Attributes:
        path (Path): Путь к файлу состояния.

    Fallbacks:
        Отсутствующий файл считается пустой базой, прочие ошибки чтения и
        сохранения представляются как PersistenceError.
    """

    def __init__(self, path: str | Path) -> None:
        """
        Сохраняет путь к файлу состояния.

        Parameters:
            path (str | Path): Путь к JSON-файлу базы данных.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Не предусмотрены.
        """
        self.path = Path(path)

    def load(self) -> dict[str, JsonValue]:
        """
        Загружает полное состояние из JSON-файла.

        Parameters:
            Не предусмотрены.

        Returns:
            dict[str, JsonValue]: Загруженное состояние базы данных.

        Fallbacks:
            При отсутствии файла возвращает пустой словарь; ошибки чтения,
            декодирования и неверный корневой тип представляются как
            PersistenceError.
        """
        try:
            with self.path.open(encoding="utf-8") as file:
                state = json.load(file)
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PersistenceError(
                f"Не удалось загрузить состояние из {self.path}"
            ) from error

        if not isinstance(state, dict):
            raise PersistenceError("Корневое значение файла базы должно быть объектом")
        return state

    def save(self, state: dict[str, JsonValue]) -> None:
        """
        Атомарно сохраняет полное состояние в JSON-файле.

        Parameters:
            state (dict[str, JsonValue]): Полное состояние для сохранения.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Ошибки сериализации и файловой системы представляются как
            PersistenceError; созданный текущей операцией временный файл
            удаляется.
        """
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    state,
                    temporary_file,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    indent=2,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, self.path)
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise PersistenceError(
                f"Не удалось сохранить состояние в {self.path}"
            ) from error
