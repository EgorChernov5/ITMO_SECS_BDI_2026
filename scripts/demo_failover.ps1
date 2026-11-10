$ErrorActionPreference = "Stop"

$routerUrl = "http://localhost:8000"
$primaryUrl = "http://localhost:8001"
$replicaUrl = "http://localhost:8002"
$mainKey = [Uri]::EscapeDataString("alpha")
$deletedKey = [Uri]::EscapeDataString("ключ")

function Wait-Condition {
    param(
        [scriptblock]$Condition,
        [string]$Description,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            if (& $Condition) {
                Write-Host "[OK] $Description"
                return
            }
        }
        catch {
            # Узлы могут временно не отвечать во время переключения.
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    throw "Превышено время ожидания: $Description"
}

Write-Host "Запуск полной топологии..."
docker compose up --build -d

Wait-Condition {
    (Invoke-RestMethod "$primaryUrl/replication/status").role -eq "primary"
} "предпочтительный узел shard-0 является primary"

Wait-Condition {
    (Invoke-RestMethod "$routerUrl/health").status -eq "ok"
} "router готов принимать запросы"

Invoke-RestMethod -Method Put -Uri "$routerUrl/kv/$mainKey" -ContentType "application/json" -Body '{"value":{"stage":"before-failover"}}'

$expectedSequence = (
    Invoke-RestMethod "$primaryUrl/replication/status"
).current_sequence
Wait-Condition {
    $status = Invoke-RestMethod "$replicaUrl/replication/status"
    (
        $status.current_sequence -eq $expectedSequence -and
        $status.lag -eq 0 -and
        $status.healthy
    )
} "реплика получила исходную запись"

Write-Host "Остановка shard-0-primary..."
docker compose stop shard-0-primary

Wait-Condition {
    $status = Invoke-RestMethod "$replicaUrl/replication/status"
    $status.role -eq "primary" -and $status.promoted -eq $true
} "shard-0-replica автоматически повышена до primary"

# Проверяем все публичные CRUD-ручки через router во время failover.
Invoke-RestMethod -Method Put -Uri "$routerUrl/kv/$mainKey" -ContentType "application/json" -Body '{"value":{"stage":"during-failover"}}'

$value = Invoke-RestMethod "$routerUrl/kv/$mainKey"
if ($value.value.stage -ne "during-failover") {
    throw "GET вернул неверное значение после promotion"
}

Invoke-RestMethod -Method Put -Uri "$routerUrl/kv/$deletedKey" -ContentType "application/json" -Body '{"value":"temporary"}'
Invoke-RestMethod -Method Delete -Uri "$routerUrl/kv/$deletedKey"

try {
    Invoke-RestMethod "$routerUrl/kv/$deletedKey"
    throw "Удалённый ключ неожиданно доступен"
}
catch {
    if ([int]$_.Exception.Response.StatusCode -ne 404) {
        throw
    }
}

$keys = Invoke-RestMethod "$routerUrl/kv"
if ($keys.keys -notcontains "alpha" -or $keys.keys -contains "ключ") {
    throw "GET /kv вернул неверный список ключей"
}

$shard = Invoke-RestMethod "$routerUrl/shards/$mainKey"
if ($shard.shard -ne "shard-0") {
    throw "Диагностическая ручка выбрала неверный сегмент"
}

if ((Invoke-RestMethod "$routerUrl/health").status -ne "ok") {
    throw "Router не прошёл health check во время failover"
}

Write-Host "Восстановление shard-0-primary..."
docker compose start shard-0-primary

Wait-Condition {
    $primary = Invoke-RestMethod "$primaryUrl/replication/status"
    $replica = Invoke-RestMethod "$replicaUrl/replication/status"
    (
        $primary.role -eq "primary" -and
        $primary.preferred_primary -eq $true -and
        $replica.role -eq "replica" -and
        $replica.promoted -eq $false -and
        $primary.current_sequence -eq $replica.current_sequence
    )
} "журнал возвращён, а исходный primary восстановил роль"

$restored = Invoke-RestMethod "$routerUrl/kv/$mainKey"
if ($restored.value.stage -ne "during-failover") {
    throw "Запись периода failover не перенесена на восстановленный primary"
}

Write-Host "[OK] Автоматические promotion и failback завершены корректно."
