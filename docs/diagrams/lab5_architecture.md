# Архитектура Lab 5

```mermaid
flowchart LR
    Client[Клиент] --> Router[Router :8000]
    Router --> S0P[shard-0-primary]
    Router --> S1P[shard-1-primary]
    S0R[shard-0-replica] -->|GET operations| S0P
    S1R[shard-1-replica] -->|GET operations| S1P
    S0P --> V0P[(volume 0 primary)]
    S0R --> V0R[(volume 0 replica)]
    S1P --> V1P[(volume 1 primary)]
    S1R --> V1R[(volume 1 replica)]
```

Router не хранит значения и не участвует в репликации. Для каждой операции с
ключом он вычисляет целое значение SHA-256 от полного UTF-8 представления и
выбирает индекс `digest % 2`. Реплики опрашивают только primary своего
сегмента, поэтому журналы и sequence-пространства независимы.
