"""Экспортирует архитектурные интерфейсы MiniKV."""

from src.interfaces.replication import IReplicationManager
from src.interfaces.sharding import IShardRouter
from src.interfaces.storage import IStorageEngine
from src.interfaces.store import IKeyValueStore

__all__ = [
    "IKeyValueStore",
    "IReplicationManager",
    "IShardRouter",
    "IStorageEngine",
]

