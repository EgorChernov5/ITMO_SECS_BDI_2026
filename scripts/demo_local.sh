#!/usr/bin/env sh

set -eu

# Изолируем демонстрацию от пользовательских файлов базы данных.
demo_directory=$(mktemp -d)
database_file="$demo_directory/data.json"
trap 'rm -rf "$demo_directory"' EXIT

uv run minikv --database-file "$database_file" put profile \
  '{"name":"Ирина","roles":["student"]}'
uv run minikv --database-file "$database_file" put counter 2

# Каждый вызов запускает новый процесс и заново загружает сохранённое состояние.
uv run minikv --database-file "$database_file" get profile
uv run minikv --database-file "$database_file" list
uv run minikv --database-file "$database_file" delete counter
uv run minikv --database-file "$database_file" list
