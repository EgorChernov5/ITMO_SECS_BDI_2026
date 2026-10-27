$ErrorActionPreference = "Stop"

function Invoke-Uv {
    & uv @args
    if ($LASTEXITCODE -ne 0) {
        throw "Команда uv завершилась с кодом $LASTEXITCODE."
    }
}

# Изолируем демонстрацию от пользовательских файлов базы данных.
$demoDirectory = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    "minikv-demo-$([guid]::NewGuid())"
$databaseFile = Join-Path $demoDirectory "data.json"
New-Item -ItemType Directory -Path $demoDirectory | Out-Null

try {
    Invoke-Uv run minikv --database-file $databaseFile put profile `
        '{\"name\":\"\u0418\u0440\u0438\u043d\u0430\",\"roles\":[\"student\"]}'
    Invoke-Uv run minikv --database-file $databaseFile put counter 2

    # Каждый вызов заново загружает состояние в отдельном процессе.
    Invoke-Uv run minikv --database-file $databaseFile get profile
    Invoke-Uv run minikv --database-file $databaseFile list
    Invoke-Uv run minikv --database-file $databaseFile delete counter
    Invoke-Uv run minikv --database-file $databaseFile list
}
finally {
    Remove-Item -LiteralPath $demoDirectory -Recurse -Force
}
