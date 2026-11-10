# Взаимодействие узлов в лабораторной работе № 4

~~~mermaid
sequenceDiagram
    participant C as Клиент
    participant P as Предпочтительный primary
    participant R as Replica
    C->>P: PUT / DELETE
    R->>P: GET operations after N
    P-->>R: упорядоченная пачка
    Note over P: остановка
    R->>P: повторные проверки
    Note over R: promotion после failover timeout
    C->>R: PUT / GET / DELETE
    Note over P: восстановление
    P->>R: GET replication status
    P->>R: POST replication/failback?after=N
    Note over R: блокировка записей и demotion
    R-->>P: операции периода failover
    Note over P: применение журнала и возврат роли primary
    R->>P: обычная pull-репликация
~~~

Контейнеры используют независимые тома. Временный primary продолжает общий
журнал только после последнего применённого номера. При восстановлении исходный
primary сначала забирает недостающий хвост журнала, после чего принимает записи.
Механизм независимо применяется к обеим парам шардов.

Схема не использует quorum или внешний координатор. Поэтому она предназначена
для демонстрации остановки процесса primary; сетевое разделение может привести
к split-brain и явно остаётся ограничением учебной реализации.
