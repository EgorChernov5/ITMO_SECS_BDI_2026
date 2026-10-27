# Взаимодействие узлов в лабораторной работе № 4

~~~mermaid
flowchart LR
    Client[Клиент] -->|PUT / DELETE| PrimaryAPI[Primary FastAPI]
    Client -->|GET| PrimaryAPI
    Client -->|GET| Replica1API[Replica 1 FastAPI]
    Client -->|GET| Replica2API[Replica 2 FastAPI]

    PrimaryAPI --> PrimaryStore[KeyValueStore]
    PrimaryStore --> PrimaryData[(primary data.json)]
    PrimaryAPI --> PrimaryLog[(primary operations.jsonl)]

    Replica1API -->|GET operations after N| PrimaryAPI
    Replica2API -->|GET operations after N| PrimaryAPI

    Replica1API --> Replica1Store[KeyValueStore]
    Replica1Store --> Replica1Data[(replica 1 data.json)]
    Replica1API --> Replica1Log[(replica 1 progress log)]

    Replica2API --> Replica2Store[KeyValueStore]
    Replica2Store --> Replica2Data[(replica 2 data.json)]
    Replica2API --> Replica2Log[(replica 2 progress log)]
~~~

Каждый контейнер использует независимый том. Реплики самостоятельно опрашивают primary, поэтому восстановление после остановки не требует отправки snapshot или ручного копирования файлов.
