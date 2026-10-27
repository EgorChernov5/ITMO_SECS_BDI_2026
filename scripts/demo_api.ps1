param(
    [string]$BaseUrl = $env:BASE_URL,
    [string]$DemoKey = $env:DEMO_KEY
)

$ErrorActionPreference = "Stop"

if (-not $BaseUrl) {
    if (Test-Path -LiteralPath ".env") {
        $configuredPort = uv run --env-file .env python -c `
            "import os; print(os.getenv('MINIKV_PORT', '8000'))"
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось прочитать MINIKV_PORT из .env."
        }
        $configuredPort = "$configuredPort".Trim()
    }
    elseif ($env:MINIKV_PORT) {
        $configuredPort = $env:MINIKV_PORT
    }
    else {
        $configuredPort = "8000"
    }
    $BaseUrl = "http://localhost:$configuredPort"
}

if (-not $DemoKey) {
    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $DemoKey = "lab3-demo-$timestamp-$PID"
}

# Проверяем готовность сервиса до изменения данных.
Invoke-RestMethod -Uri "$BaseUrl/health" | ConvertTo-Json -Compress

# Изолированный ключ делает сценарий повторяемым для непустой базы.
$body = @{
    value = @{ message = "hello"; version = 1 }
} | ConvertTo-Json -Depth 10 -Compress

Invoke-RestMethod `
    -Method Put `
    -Uri "$BaseUrl/kv/$DemoKey" `
    -ContentType "application/json; charset=utf-8" `
    -Body $body | Out-Null
Invoke-RestMethod -Uri "$BaseUrl/kv/$DemoKey" |
    ConvertTo-Json -Depth 10 -Compress

$body = @{
    value = @{ message = "updated"; version = 2 }
} | ConvertTo-Json -Depth 10 -Compress

Invoke-RestMethod `
    -Method Put `
    -Uri "$BaseUrl/kv/$DemoKey" `
    -ContentType "application/json; charset=utf-8" `
    -Body $body | Out-Null
Invoke-RestMethod -Uri "$BaseUrl/kv/$DemoKey" |
    ConvertTo-Json -Depth 10 -Compress
Invoke-RestMethod -Uri "$BaseUrl/kv" | ConvertTo-Json -Depth 10 -Compress

Invoke-RestMethod -Method Delete -Uri "$BaseUrl/kv/$DemoKey" | Out-Null
