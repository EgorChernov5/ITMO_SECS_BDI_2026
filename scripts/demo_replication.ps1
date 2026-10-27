param(
    [string]$PrimaryUrl = $env:PRIMARY_URL,
    [string]$ReplicaUrl = $env:REPLICA_URL,
    [string]$PrimaryService = "shard-0-primary",
    [string]$ReplicaService = "shard-0-replica",
    [string]$DemoKey = ""
)

$ErrorActionPreference = "Stop"

function Get-ComposeUrl {
    param([string]$Service, [string]$FallbackPort)

    $binding = docker compose port $Service 8000
    if ($LASTEXITCODE -eq 0 -and $binding) {
        $publishedPort = ($binding.Trim() -split ":")[-1]
        return "http://localhost:$publishedPort"
    }
    return "http://localhost:$FallbackPort"
}

if (-not $PrimaryUrl) {
    $fallback = if ($env:MINIKV_SHARD_0_PRIMARY_PORT) {
        $env:MINIKV_SHARD_0_PRIMARY_PORT
    }
    else {
        "8001"
    }
    $PrimaryUrl = Get-ComposeUrl -Service $PrimaryService -FallbackPort $fallback
}
if (-not $ReplicaUrl) {
    $fallback = if ($env:MINIKV_SHARD_0_REPLICA_PORT) {
        $env:MINIKV_SHARD_0_REPLICA_PORT
    }
    else {
        "8002"
    }
    $ReplicaUrl = Get-ComposeUrl -Service $ReplicaService -FallbackPort $fallback
}
if (-not $DemoKey) {
    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $DemoKey = "lab4-demo-$timestamp-$PID"
}

function Wait-ReplicationSequence {
    param([string]$BaseUrl, [int]$ExpectedSequence)

    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $status = Invoke-RestMethod -Uri "$BaseUrl/replication/status"
            if (
                $status.current_sequence -eq $ExpectedSequence -and
                $status.lag -eq 0 -and
                $status.healthy
            ) {
                return
            }
        }
        catch {
            # Временная недоступность ожидается во время запуска контейнера.
        }
        Start-Sleep -Seconds 1
    }
    throw "Реплика $BaseUrl не достигла операции $ExpectedSequence."
}

# Записываем значение напрямую в primary выбранного сегмента.
$body = @{ value = @{ stage = 1 } } | ConvertTo-Json -Compress
$put = @{
    Method = "Put"
    Uri = "$PrimaryUrl/kv/$DemoKey"
    ContentType = "application/json; charset=utf-8"
    Body = $body
}
Invoke-RestMethod @put | Out-Null
$sequence = (
    Invoke-RestMethod -Uri "$PrimaryUrl/replication/status"
).current_sequence
Wait-ReplicationSequence -BaseUrl $ReplicaUrl -ExpectedSequence $sequence
Invoke-RestMethod -Uri "$ReplicaUrl/kv/$DemoKey" |
    ConvertTo-Json -Compress

# Останавливаем реплику, меняем primary и проверяем догоняющую синхронизацию.
docker compose stop $ReplicaService
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось остановить сервис $ReplicaService."
}

$body = @{ value = @{ stage = 2 } } | ConvertTo-Json -Compress
$put.Body = $body
Invoke-RestMethod @put | Out-Null
Invoke-RestMethod -Method Delete -Uri "$PrimaryUrl/kv/$DemoKey" | Out-Null

docker compose start $ReplicaService
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось запустить сервис $ReplicaService."
}

$sequence = (
    Invoke-RestMethod -Uri "$PrimaryUrl/replication/status"
).current_sequence
Wait-ReplicationSequence -BaseUrl $ReplicaUrl -ExpectedSequence $sequence

try {
    Invoke-RestMethod -Uri "$ReplicaUrl/kv/$DemoKey" | Out-Null
    throw "После синхронизации ключ не должен существовать."
}
catch {
    if (-not $_.Exception.Response) {
        throw
    }
    if ([int]$_.Exception.Response.StatusCode -ne 404) {
        throw
    }
}

Invoke-RestMethod -Uri "$ReplicaUrl/replication/status" |
    ConvertTo-Json -Compress
Write-Host "Сценарий восстановления $ReplicaService завершён."
