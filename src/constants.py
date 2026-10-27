"""Содержит общие константы контрактов и конфигурации MiniKV."""

from pathlib import Path

MIN_KEY_LENGTH = 1
DEFAULT_DATA_FILE = Path("data/data.json")
DEFAULT_REPLICATION_POLL_INTERVAL = 1.0
DEFAULT_REPLICATION_BATCH_SIZE = 100
DEFAULT_REPLICATION_REQUEST_TIMEOUT = 5.0
