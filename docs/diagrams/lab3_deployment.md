# Развёртывание MiniKV в лабораторной работе № 3

```mermaid
flowchart LR
    Client[Удалённый клиент / curl]
    Port[Порт хоста 8000]
    API[Контейнер primary / FastAPI<br/>0.0.0.0:8000]
    Store[KeyValueStore]
    Engine[JsonStorage]
    Volume[(minikv-data<br/>/data/data.json)]

    Client -->|HTTP| Port
    Port --> API
    API --> Store
    Store --> Engine
    Engine --> Volume
```

Compose публикует порт контейнера `primary` через `${MINIKV_PORT:-8000}` и
монтирует именованный том `minikv-data` в `/data`. Имя тома сохранено после
добавления репликации, поэтому данные односервисного развёртывания третьей
лабораторной работы остаются доступны основному узлу. Пересоздание контейнера
не удаляет том, и новый экземпляр приложения загружает сохранённый JSON-файл.
