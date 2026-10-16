# Диаграмма компонентов лабораторной работы № 1

```mermaid
classDiagram
    direction LR
    class IKeyValueStore {
        <<interface>>
        +put(key: str, value: JsonValue) None
        +get(key: str) JsonValue
        +delete(key: str) None
        +list_keys() list~str~
    }
    class IStorageEngine {
        <<interface>>
        +load() dict~str, JsonValue~
        +save(state: dict~str, JsonValue~) None
    }
    class IReplicationManager {
        <<interface>>
        +publish(mutation: Mutation) None
        +apply(mutations: list~Mutation~) None
    }
    class IShardRouter {
        <<interface>>
        +route(key: str) Shard
    }
    class KeyValueStoreStub
    class StorageEngineStub
    class ReplicationManagerStub
    class ShardRouterStub

    IKeyValueStore --> IStorageEngine : использует
    KeyValueStoreStub ..|> IKeyValueStore
    StorageEngineStub ..|> IStorageEngine
    ReplicationManagerStub ..|> IReplicationManager
    ShardRouterStub ..|> IShardRouter
    IKeyValueStore ..> IReplicationManager : будущие записи
    IShardRouter ..> IKeyValueStore : будущие запросы
```

Сплошная зависимость показывает единственное действующее направление между
контрактами первой лабораторной работы. Пунктирные зависимости зарезервированы
для последующих этапов и пока не имеют реализации.

