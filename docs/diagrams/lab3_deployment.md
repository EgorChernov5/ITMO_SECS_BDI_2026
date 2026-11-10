# Развёртывание MiniKV в лабораторной работе № 3

```mermaid
flowchart LR
    Client[Удалённый клиент / curl]
    Port[Порт хоста 8001 по умолчанию]
    API[Контейнер shard-0-primary / FastAPI<br/>0.0.0.0:8000]
    Store[KeyValueStore]
    Engine[JsonStorage]
    Volume[(shard-0-primary-data<br/>/data/data.json)]

    Client -->|HTTP| Port
    Port --> API
    API --> Store
    Store --> Engine
    Engine --> Volume
```

Compose публикует порт контейнера `shard-0-primary` через
`${MINIKV_SHARD_0_PRIMARY_PORT:-8001}` и монтирует именованный том
`shard-0-primary-data` в `/data`. Запуск только этого сервиса воспроизводит
односервисное развёртывание третьей лабораторной работы. Пересоздание контейнера
не удаляет том, и новый экземпляр приложения загружает сохранённый JSON-файл.
