"""Предоставляет командную строку для локальной базы данных MiniKV."""

import argparse
import json
import sys
from pathlib import Path

from src.errors import MiniKVError
from src.storage import JsonStorage
from src.store import KeyValueStore


def build_parser() -> argparse.ArgumentParser:
    """
    Создаёт парсер командной строки MiniKV.

    Parameters:
        Не предусмотрены.

    Returns:
        argparse.ArgumentParser: Настроенный парсер командной строки.

    Fallbacks:
        Не предусмотрены.
    """
    parser = argparse.ArgumentParser(description="Локальная база данных MiniKV")
    parser.add_argument(
        "--database-file",
        type=Path,
        default=Path("data/data.json"),
        help="путь к JSON-файлу базы данных (по умолчанию: data/data.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    put_parser = subparsers.add_parser("put", help="создать или заменить значение")
    put_parser.add_argument("key", help="непустой строковый ключ")
    put_parser.add_argument("value", help="значение в формате JSON")

    get_parser = subparsers.add_parser("get", help="получить значение")
    get_parser.add_argument("key", help="непустой строковый ключ")

    delete_parser = subparsers.add_parser("delete", help="удалить значение")
    delete_parser.add_argument("key", help="непустой строковый ключ")

    subparsers.add_parser("list", help="получить отсортированный список ключей")
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Выполняет выбранную операцию MiniKV.

    Parameters:
        argv (list[str] | None): Аргументы без имени программы. По умолчанию:
            None, при котором используются аргументы процесса.

    Returns:
        int: Нулевой код при успехе и единица при известной ошибке.

    Fallbacks:
        Ошибки предметной области и неверные значения выводятся без трассировки
        в stderr и завершают команду с кодом 1.
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        store = KeyValueStore(JsonStorage(arguments.database_file))
        if arguments.command == "put":
            try:
                value = json.loads(arguments.value)
            except json.JSONDecodeError as error:
                raise ValueError("Значение должно быть корректным JSON") from error
            store.put(arguments.key, value)
        elif arguments.command == "get":
            print(json.dumps(store.get(arguments.key), ensure_ascii=False))
        elif arguments.command == "delete":
            store.delete(arguments.key)
        else:
            print(json.dumps(store.list_keys(), ensure_ascii=False))
    except (MiniKVError, ValueError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
