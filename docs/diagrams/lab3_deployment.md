# Развёртывание MiniKV в лабораторной работе № 3

```mermaid
flowchart LR
    Client[Удалённый клиент / curl]
    Port[Порт хоста 8000]
    API[Контейнер FastAPI<br/>0.0.0.0:8000]
    Store[KeyValueStore]
    Engine[JsonStorage]
    Volume[(minikv-data<br/>/data/data.json)]

    Client -->|HTTP| Port
    Port --> API
    API --> Store
    Store --> Engine
    Engine --> Volume
```

Compose публикует порт контейнера через `${MINIKV_PORT:-8000}` и монтирует
именованный том `minikv-data` в `/data`. Пересоздание контейнера не удаляет том,
поэтому новый экземпляр приложения загружает ранее сохранённый JSON-файл.
