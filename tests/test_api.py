"""Проверяет REST API третьей лабораторной работы."""

from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from src.api.app import create_app, get_store
from src.errors import PersistenceError
from src.interfaces import IKeyValueStore


def test_put_get_overwrite_and_list(tmp_path: Path) -> None:
    """
    Проверяет создание, чтение, замену и перечисление через REST API.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    client = TestClient(create_app(tmp_path / "data.json"))

    assert client.put("/kv/zeta", json={"value": 1}).status_code == 204
    assert client.put("/kv/alpha", json={"value": [1, 2]}).status_code == 204
    assert client.put(
        "/kv/zeta",
        json={"value": {"version": 2}},
    ).status_code == 204

    assert client.get("/kv/zeta").json() == {"value": {"version": 2}}
    assert client.get("/kv").json() == {"keys": ["alpha", "zeta"]}


def test_delete_and_missing_key_responses(tmp_path: Path) -> None:
    """
    Проверяет удаление и ответы для отсутствующего ключа.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    client = TestClient(create_app(tmp_path / "data.json"))
    client.put("/kv/temporary", json={"value": True})

    assert client.delete("/kv/temporary").status_code == 204
    assert client.get("/kv/temporary").status_code == 404
    assert client.delete("/kv/temporary").status_code == 404


def test_invalid_request_keeps_fastapi_validation_response(tmp_path: Path) -> None:
    """
    Проверяет стандартный HTTP 422 для некорректного тела запроса.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    client = TestClient(create_app(tmp_path / "data.json"))

    response = client.put("/kv/profile", json={})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_health_reports_ready_store(tmp_path: Path) -> None:
    """
    Проверяет успешный ответ endpoint готовности.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    client = TestClient(create_app(tmp_path / "data.json"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_hides_unavailable_storage_details(tmp_path: Path) -> None:
    """
    Проверяет безопасный HTTP 503 при недоступности хранилища.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        В ответ не попадает путь из исходной ошибки.
    """
    application = create_app(tmp_path / "data.json")
    unavailable_store = Mock(spec=IKeyValueStore)
    unavailable_store.list_keys.side_effect = PersistenceError(
        "Сбой в C:/secret/data.json"
    )

    def override_store() -> IKeyValueStore:
        """
        Возвращает имитацию недоступного хранилища.

        Parameters:
            Не предусмотрены.

        Returns:
            IKeyValueStore: Имитация хранилища.

        Fallbacks:
            Не предусмотрены.
        """
        return unavailable_store

    application.dependency_overrides[get_store] = override_store
    response = TestClient(application).get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Хранилище недоступно"}
    assert "secret" not in response.text


def test_persistence_error_response_hides_file_path(tmp_path: Path) -> None:
    """
    Проверяет безопасный HTTP 500 при сбое постоянного хранилища.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        В ответ не попадает путь из исходной ошибки.
    """
    application = create_app(tmp_path / "data.json")
    failed_store = Mock(spec=IKeyValueStore)
    failed_store.list_keys.side_effect = PersistenceError(
        "Сбой в C:/secret/data.json"
    )

    def override_store() -> IKeyValueStore:
        """
        Возвращает имитацию хранилища со сбоем чтения.

        Parameters:
            Не предусмотрены.

        Returns:
            IKeyValueStore: Имитация хранилища.

        Fallbacks:
            Не предусмотрены.
        """
        return failed_store

    application.dependency_overrides[get_store] = override_store
    response = TestClient(application).get("/kv")

    assert response.status_code == 500
    assert response.json() == {"detail": "Ошибка постоянного хранилища"}
    assert "secret" not in response.text


def test_data_survives_application_reconstruction(tmp_path: Path) -> None:
    """
    Проверяет восстановление данных после пересоздания приложения.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        Не предусмотрены.
    """
    path = tmp_path / "data.json"
    first_client = TestClient(create_app(path))
    first_client.put("/kv/persistent", json={"value": {"saved": True}})

    restarted_client = TestClient(create_app(path))

    assert restarted_client.get("/kv/persistent").json() == {
        "value": {"saved": True}
    }


def test_unexpected_error_response_hides_internal_details(tmp_path: Path) -> None:
    """
    Проверяет безопасный HTTP 500 для непредвиденного исключения.

    Parameters:
        tmp_path (Path): Временный каталог pytest.

    Returns:
        None: Тест не возвращает значение.

    Fallbacks:
        В ответ не попадают трассировка и внутреннее сообщение.
    """
    application = create_app(tmp_path / "data.json")
    failed_store = Mock(spec=IKeyValueStore)
    failed_store.get.side_effect = RuntimeError("Секретная внутренняя ошибка")

    def override_store() -> IKeyValueStore:
        """
        Возвращает имитацию хранилища с непредвиденным сбоем.

        Parameters:
            Не предусмотрены.

        Returns:
            IKeyValueStore: Имитация хранилища.

        Fallbacks:
            Не предусмотрены.
        """
        return failed_store

    application.dependency_overrides[get_store] = override_store
    response = TestClient(
        application,
        raise_server_exceptions=False,
    ).get("/kv/failure")

    assert response.status_code == 500
    assert response.json() == {"detail": "Внутренняя ошибка сервиса"}
    assert "Секретная" not in response.text
