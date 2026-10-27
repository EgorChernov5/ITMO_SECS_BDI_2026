param(
    [string]$PrimaryUrl = $env:PRIMARY_URL,
    [string]$Replica1Url = $env:REPLICA_1_URL,
    [string]$Replica2Url = $env:REPLICA_2_URL,
    [string]$DemoKey = ""
)

$ErrorActionPreference = "Stop"

function Get-ComposeUrl {
    param(
        [string]$Service,
        [string]$FallbackPort
    )

    $binding = docker compose port $Service 8000
    if ($LASTEXITCODE -eq 0 -and $binding) {
        $publishedPort = ($binding.Trim() -split ":")[-1]
        return "http://localhost:$publishedPort"
    }
    return "http://localhost:$FallbackPort"
}

if (-not $PrimaryUrl) {
    $fallback = if ($env:MINIKV_PORT) { $env:MINIKV_PORT } else { "8000" }
    $PrimaryUrl = Get-ComposeUrl -Service "primary" -FallbackPort $fallback
}
if (-not $Replica1Url) {
    $fallback = if ($env:MINIKV_REPLICA_1_PORT) {
        $env:MINIKV_REPLICA_1_PORT
    }
    else {
        "8001"
    }
    $Replica1Url = Get-ComposeUrl -Service "replica-1" -FallbackPort $fallback
}
if (-not $Replica2Url) {
    $fallback = if ($env:MINIKV_REPLICA_2_PORT) {
        $env:MINIKV_REPLICA_2_PORT
    }
    else {
        "8002"
    }
    $Replica2Url = Get-ComposeUrl -Service "replica-2" -FallbackPort $fallback
}
if (-not $DemoKey) {
    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $DemoKey = "lab4-demo-$timestamp-$PID"
}

function Wait-ReplicationSequence {
    param(
        [string]$BaseUrl,
        [int]$ExpectedSequence
    )

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

# Записываем первое значение и ждём обе реплики.
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
Wait-ReplicationSequence -BaseUrl $Replica1Url -ExpectedSequence $sequence
Wait-ReplicationSequence -BaseUrl $Replica2Url -ExpectedSequence $sequence
Invoke-RestMethod -Uri "$Replica1Url/kv/$DemoKey" | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "$Replica2Url/kv/$DemoKey" | ConvertTo-Json -Compress

# Останавливаем вторую реплику и проверяем догоняющую синхронизацию.
docker compose stop replica-2
$body = @{ value = @{ stage = 2 } } | ConvertTo-Json -Compress
$put.Body = $body
Invoke-RestMethod @put | Out-Null
Invoke-RestMethod -Method Delete -Uri "$PrimaryUrl/kv/$DemoKey" | Out-Null
docker compose start replica-2

$sequence = (
    Invoke-RestMethod -Uri "$PrimaryUrl/replication/status"
).current_sequence
Wait-ReplicationSequence -BaseUrl $Replica2Url -ExpectedSequence $sequence

try {
    Invoke-RestMethod -Uri "$Replica2Url/kv/$DemoKey" | Out-Null
    throw "После синхронизации ключ не должен существовать."
}
catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 404) {
        throw
    }
}

Invoke-RestMethod -Uri "$Replica2Url/replication/status" |
    ConvertTo-Json -Compress
Write-Host "Сценарий остановки и восстановления реплики завершён."
