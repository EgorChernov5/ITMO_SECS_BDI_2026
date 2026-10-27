# ITMO_SECS_BDI_2026

Educational MiniKV project for the Big Data Infrastructures course.

The project is developed incrementally: every laboratory assignment extends the
same key-value database and preserves the behavior delivered by earlier labs.
The overall scope and constraints are defined in [en_plan.md](tmp/en_plan.md).

## Implementation roadmap

1. [Lab 1 - interfaces and architecture](tmp/plan_for_lab_1.md)
2. [Lab 2 - local persistent database](tmp/plan_for_lab_2.md)
3. [Lab 3 - REST API and container deployment](tmp/plan_for_lab_3.md)
4. [Lab 4 - primary-replica replication](tmp/plan_for_lab_4.md)
5. [Lab 5 - sharding with replication](tmp/plan_for_lab_5.md)

Each plan is a milestone specification. It lists its dependency on the previous
lab, the intended file changes, implementation order, verification scenarios,
defense artifacts, and a completion gate.

## Implemented milestones

### Lab 1 — architecture

The first milestone defines four implementation-independent contracts:

- IKeyValueStore exposes put, get, delete, and sorted list_keys;
- IStorageEngine loads and atomically saves the complete state;
- IReplicationManager publishes and applies ordered mutations;
- IShardRouter maps a key to a configured shard.

The store depends on the storage engine, while storage never depends on the
store. Replication and sharding are contract-only extension points for Labs 4
and 5. The stubs fail explicitly and do not persist data or emulate later
functionality.

See [the Lab 1 report](docs/lab1.md) and
[the component diagram](docs/diagrams/lab1_components.md) for details.

### Lab 2 — local persistence

The second milestone provides a working `KeyValueStore`, an atomic JSON storage
engine, and a CLI. For example:

```bash
uv run minikv --database-file data/data.json put greeting '"hello"'
uv run minikv --database-file data/data.json get greeting
uv run minikv --database-file data/data.json list
uv run minikv --database-file data/data.json delete greeting
```

Runtime database files are ignored by Git. A safe example document is available
at [data/data.example.json](data/data.example.json). See
[the Lab 2 report](docs/lab2.md) for the architecture, demonstration, and
verification commands.

### Lab 3 — REST API and containers

The third milestone exposes the persistent store through FastAPI and packages
it as a non-root Docker Compose service with a named data volume:

```bash
docker compose up --build -d
sh scripts/demo_api.sh
```

In PowerShell, use its built-in HTTP client and the PowerShell demo script
instead of the Unix-specific `curl` and `sh` commands:

```powershell
docker compose up --build -d
.\scripts\demo_api.ps1
```

For local startup, both `MINIKV_DATA_FILE` and `MINIKV_PORT` can be loaded
from the root `.env` file:

```bash
uv run --env-file .env minikv-api
```

OpenAPI documentation is available at the configured port. Docker Compose also
reads `.env` automatically and uses `MINIKV_PORT` as the published host port. See [the Lab 3 report](docs/lab3.md) and
[the deployment diagram](docs/diagrams/lab3_deployment.md) for the endpoint
contract, remote-access example, and persistence verification procedure.
