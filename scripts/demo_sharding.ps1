param(
    [string]$RouterUrl = $env:ROUTER_URL,
    [string]$Shard0PrimaryUrl = $env:SHARD_0_PRIMARY_URL,
    [string]$Shard0ReplicaUrl = $env:SHARD_0_REPLICA_URL,
    [string]$Shard1PrimaryUrl = $env:SHARD_1_PRIMARY_URL,
    [string]$Shard1ReplicaUrl = $env:SHARD_1_REPLICA_URL,
    [string]$DemoPrefix = ""
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

function Wait-ReplicationSequence {
    param([string]$PrimaryUrl, [string]$ReplicaUrl)

    $expected = (
        Invoke-RestMethod -Uri "$PrimaryUrl/replication/status"
    ).current_sequence
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $status = Invoke-RestMethod -Uri "$ReplicaUrl/replication/status"
            if (
                $status.current_sequence -eq $expected -and
                $status.lag -eq 0 -and
                $status.healthy
            ) {
                return
            }
        }
        catch {
            # Реплика может быть временно недоступна во время запуска.
        }
        Start-Sleep -Seconds 1
    }
    throw "Реплика $ReplicaUrl не достигла операции $expected."
}

function Assert-MissingKey {
    param([string]$Url)

    try {
        Invoke-RestMethod -Uri $Url | Out-Null
        throw "Для чужого сегмента ожидался HTTP 404: $Url"
    }
    catch {
        if (-not $_.Exception.Response) {
            throw
        }
        if ([int]$_.Exception.Response.StatusCode -ne 404) {
            throw
        }
    }
}

if (-not $RouterUrl) {
    $fallback = if ($env:MINIKV_PORT) { $env:MINIKV_PORT } else { "8000" }
    $RouterUrl = Get-ComposeUrl -Service "router" -FallbackPort $fallback
}
if (-not $Shard0PrimaryUrl) {
    $fallback = if ($env:MINIKV_SHARD_0_PRIMARY_PORT) {
        $env:MINIKV_SHARD_0_PRIMARY_PORT
    }
    else {
        "8001"
    }
    $Shard0PrimaryUrl = Get-ComposeUrl -Service "shard-0-primary" -FallbackPort $fallback
}
if (-not $Shard0ReplicaUrl) {
    $fallback = if ($env:MINIKV_SHARD_0_REPLICA_PORT) {
        $env:MINIKV_SHARD_0_REPLICA_PORT
    }
    else {
        "8002"
    }
    $Shard0ReplicaUrl = Get-ComposeUrl -Service "shard-0-replica" -FallbackPort $fallback
}
if (-not $Shard1PrimaryUrl) {
    $fallback = if ($env:MINIKV_SHARD_1_PRIMARY_PORT) {
        $env:MINIKV_SHARD_1_PRIMARY_PORT
    }
    else {
        "8003"
    }
    $Shard1PrimaryUrl = Get-ComposeUrl -Service "shard-1-primary" -FallbackPort $fallback
}
if (-not $Shard1ReplicaUrl) {
    $fallback = if ($env:MINIKV_SHARD_1_REPLICA_PORT) {
        $env:MINIKV_SHARD_1_REPLICA_PORT
    }
    else {
        "8004"
    }
    $Shard1ReplicaUrl = Get-ComposeUrl -Service "shard-1-replica" -FallbackPort $fallback
}
if (-not $DemoPrefix) {
    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $DemoPrefix = "lab5-demo-$timestamp-$PID"
}

$key0 = ""
$key1 = ""
for ($index = 0; $index -le 100; $index++) {
    $candidate = "$DemoPrefix-$index"
    $routing = Invoke-RestMethod -Uri "$RouterUrl/shards/$candidate"
    if ($routing.shard -eq "shard-0" -and -not $key0) {
        $key0 = $candidate
    }
    elseif ($routing.shard -eq "shard-1" -and -not $key1) {
        $key1 = $candidate
    }
    if ($key0 -and $key1) {
        break
    }
}
if (-not $key0 -or -not $key1) {
    throw "Не удалось подобрать ключи для обоих сегментов."
}

# Все клиентские изменения выполняются только через единый адрес router.
$body = @{ value = @{ shard = 0 } } | ConvertTo-Json -Compress
$put0 = @{
    Method = "Put"
    Uri = "$RouterUrl/kv/$key0"
    ContentType = "application/json; charset=utf-8"
    Body = $body
}
Invoke-RestMethod @put0 | Out-Null

$body = @{ value = @{ shard = 1 } } | ConvertTo-Json -Compress
$put1 = @{
    Method = "Put"
    Uri = "$RouterUrl/kv/$key1"
    ContentType = "application/json; charset=utf-8"
    Body = $body
}
Invoke-RestMethod @put1 | Out-Null

Wait-ReplicationSequence -PrimaryUrl $Shard0PrimaryUrl -ReplicaUrl $Shard0ReplicaUrl
Wait-ReplicationSequence -PrimaryUrl $Shard1PrimaryUrl -ReplicaUrl $Shard1ReplicaUrl

Invoke-RestMethod -Uri "$RouterUrl/kv/$key0" | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "$RouterUrl/kv/$key1" | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "$RouterUrl/kv" | ConvertTo-Json -Compress

# Подтверждаем наличие только в выбранной паре primary-replica.
Invoke-RestMethod -Uri "$Shard0PrimaryUrl/kv/$key0" | Out-Null
Invoke-RestMethod -Uri "$Shard0ReplicaUrl/kv/$key0" | Out-Null
Invoke-RestMethod -Uri "$Shard1PrimaryUrl/kv/$key1" | Out-Null
Invoke-RestMethod -Uri "$Shard1ReplicaUrl/kv/$key1" | Out-Null

Assert-MissingKey -Url "$Shard1PrimaryUrl/kv/$key0"
Assert-MissingKey -Url "$Shard1ReplicaUrl/kv/$key0"
Assert-MissingKey -Url "$Shard0PrimaryUrl/kv/$key1"
Assert-MissingKey -Url "$Shard0ReplicaUrl/kv/$key1"

Write-Host "Ключ $key0 находится в shard-0, ключ $key1 — в shard-1."
