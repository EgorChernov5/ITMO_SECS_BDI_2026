#!/usr/bin/env bash
set -euo pipefail

resolve_compose_url() {
    local service="$1"
    local fallback_port="$2"
    local binding
    binding="$(docker compose port "$service" 8000 2>/dev/null || true)"
    if [[ -n "$binding" ]]; then
        echo "http://localhost:${binding##*:}"
    else
        echo "http://localhost:$fallback_port"
    fi
}

primary_url="${PRIMARY_URL:-$(resolve_compose_url primary "${MINIKV_PORT:-8000}")}"
replica_1_url="${REPLICA_1_URL:-$(resolve_compose_url replica-1 "${MINIKV_REPLICA_1_PORT:-8001}")}"
replica_2_url="${REPLICA_2_URL:-$(resolve_compose_url replica-2 "${MINIKV_REPLICA_2_PORT:-8002}")}"
demo_key="${DEMO_KEY:-lab4-demo-$(date +%s)-$$}"

wait_for_sequence() {
    local url="$1"
    local expected="$2"
    local attempt status current lag healthy
    for attempt in $(seq 1 30); do
        status="$(curl --fail --silent "$url/replication/status" || true)"
        if [[ -n "$status" ]]; then
            current="$(uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["current_sequence"])' "$status")"
            lag="$(uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["lag"])' "$status")"
            healthy="$(uv run python -c 'import json,sys; print(str(json.loads(sys.argv[1])["healthy"]).lower())' "$status")"
            if [[ "$current" == "$expected" && "$lag" == "0" && "$healthy" == "true" ]]; then
                return 0
            fi
        fi
        sleep 1
    done
    echo "Реплика $url не достигла операции $expected." >&2
    return 1
}

# Записываем первое значение и ждём обе реплики.
curl --fail --silent --show-error -X PUT "$primary_url/kv/$demo_key" -H "Content-Type: application/json" -d '{"value":{"stage":1}}'
status="$(curl --fail --silent "$primary_url/replication/status")"
sequence="$(uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["current_sequence"])' "$status")"
wait_for_sequence "$replica_1_url" "$sequence"
wait_for_sequence "$replica_2_url" "$sequence"
curl --fail --silent "$replica_1_url/kv/$demo_key"
curl --fail --silent "$replica_2_url/kv/$demo_key"

# Останавливаем вторую реплику, меняем primary и запускаем догоняющую синхронизацию.
docker compose stop replica-2
curl --fail --silent --show-error -X PUT "$primary_url/kv/$demo_key" -H "Content-Type: application/json" -d '{"value":{"stage":2}}'
curl --fail --silent --show-error -X DELETE "$primary_url/kv/$demo_key"
docker compose start replica-2

status="$(curl --fail --silent "$primary_url/replication/status")"
sequence="$(uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["current_sequence"])' "$status")"
wait_for_sequence "$replica_2_url" "$sequence"

code="$(curl --silent --output /dev/null --write-out '%{http_code}' "$replica_2_url/kv/$demo_key")"
if [[ "$code" != "404" ]]; then
    echo "После синхронизации ожидался HTTP 404, получен $code." >&2
    exit 1
fi

curl --fail --silent "$replica_2_url/replication/status"
echo
echo "Сценарий остановки и восстановления реплики завершён."
