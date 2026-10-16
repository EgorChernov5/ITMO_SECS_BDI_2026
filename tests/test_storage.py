"""Проверяет локальное хранение и операции второй лабораторной работы."""

import json
from pathlib import Path

import pytest

from src.errors import KeyNotFoundError, PersistenceError
from src.storage import JsonStorage
from src.store import KeyValueStore


def test_new_database_persists_put_and_sorted_keys(tmp_path: Path) -> None:
    """
    Проверяет создание файла, запись и детерминированный список ключей.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    path = tmp_path / "data.json"
    store = KeyValueStore(JsonStorage(path))

    store.put("zeta", {"enabled": True})
    store.put("alpha", [1, 2, 3])

    assert store.list_keys() == ["alpha", "zeta"]
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "alpha": [1, 2, 3],
        "zeta": {"enabled": True},
    }


def test_overwrite_read_and_restart_recovery(tmp_path: Path) -> None:
    """
    Проверяет замену значения, чтение и восстановление в новом экземпляре.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    path = tmp_path / "data.json"
    store = KeyValueStore(JsonStorage(path))
    store.put("profile", {"name": "Ирина"})
    store.put("profile", {"name": "Ирина", "active": True})

    restarted_store = KeyValueStore(JsonStorage(path))

    assert restarted_store.get("profile") == {
        "name": "Ирина",
        "active": True,
    }


def test_delete_persists_and_missing_keys_raise(tmp_path: Path) -> None:
    """
    Проверяет удаление и единое поведение отсутствующих ключей.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    path = tmp_path / "data.json"
    store = KeyValueStore(JsonStorage(path))
    store.put("temporary", 42)
    store.delete("temporary")

    assert KeyValueStore(JsonStorage(path)).list_keys() == []
    with pytest.raises(KeyNotFoundError):
        store.get("temporary")
    with pytest.raises(KeyNotFoundError):
        store.delete("temporary")


def test_get_and_put_do_not_expose_mutable_state(tmp_path: Path) -> None:
    """
    Проверяет независимость внутреннего состояния от объектов вызывающей стороны.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    source = {"items": [1]}
    store = KeyValueStore(JsonStorage(tmp_path / "data.json"))
    store.put("document", source)
    source["items"].append(2)

    loaded = store.get("document")
    loaded["items"].append(3)

    assert store.get("document") == {"items": [1]}


def test_malformed_and_non_object_files_raise_persistence_error(
    tmp_path: Path,
) -> None:
    """
    Проверяет отказ при повреждённом JSON и неверном корневом значении.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    path = tmp_path / "data.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(PersistenceError):
        KeyValueStore(JsonStorage(path))

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(PersistenceError):
        KeyValueStore(JsonStorage(path))


def test_invalid_values_are_rejected(tmp_path: Path) -> None:
    """
    Проверяет отклонение значений вне строгой модели JSON.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    store = KeyValueStore(JsonStorage(tmp_path / "data.json"))

    with pytest.raises(ValueError):
        store.put("tuple", (1, 2))
    with pytest.raises(ValueError):
        store.put("infinite", float("inf"))


def test_failed_replace_preserves_file_and_store_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяет сохранность последнего состояния при сбое атомарной замены.

    Parameters:
        tmp_path (Path): Временный каталог pytest.
        monkeypatch (pytest.MonkeyPatch): Средство временной замены функций.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    path = tmp_path / "data.json"
    store = KeyValueStore(JsonStorage(path))
    store.put("stable", {"version": 1})
    original_contents = path.read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        """
        Имитирует отказ файловой системы при атомарной замене.

        Parameters:
            source (Path): Путь к временному файлу.
            destination (Path): Путь к целевому файлу.

        Returns:
            None: Метод не возвращает значение.

        Fallbacks:
            Всегда возбуждает OSError.
        """
        raise OSError("имитация отказа замены")

    monkeypatch.setattr("src.storage.json_storage.os.replace", fail_replace)

    with pytest.raises(PersistenceError):
        store.put("unstable", {"version": 2})

    assert path.read_bytes() == original_contents
    assert store.list_keys() == ["stable"]
    assert list(tmp_path.glob("*.tmp")) == []
