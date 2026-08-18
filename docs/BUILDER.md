# Builder worker and harness sessions

The **builder** definition is a spawnable software-builder (not a
newsroom desk). It has workspace file tools, persistent `memory.md`,
and a workspace-sandboxed `run_command` shell.

## How Chief of Staff creates a builder session

Sessions live on the control plane (sg02). `POST /sessions` enqueues a
Task on `queue:puller:{target_puller}`. Factory reporter/editor use
`puller-01`. Builder work must **not** use that name.

```bash
# Preferred once control-plane understands `definition` (PR on CP):
curl -sS -X POST http://sg02:8000/sessions \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Add a /health route and a test","definition":"builder"}'

# Works on the live session API today (no CP deploy required):
curl -sS -X POST http://sg02:8000/sessions \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Add a /health route and a test","target_puller":"builder-01","model":"qwen3.5:27b"}'
```

| Field | Builder value | Why |
| --- | --- | --- |
| `goal` | the software task | becomes the run goal / first user message |
| `definition` | `builder` | selects this agent definition; defaults `target_puller` to `builder-01` |
| `target_puller` | `builder-01` | inbox the builder worker claims (`GET /tasks/next`) |
| `model` | optional | forwarded to the LLM puller (`puller-01`) |

Poll with `GET /sessions/{id}` and follow up with
`POST /sessions/{id}/messages`.

Do **not** send builder goals to `puller-01` — that queue is the
factory LLM worker (reporter/editor).

## Spawn a builder instance on a node (direct)

If agentnet-node gateway is running:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/definitions/builder/spawn \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "autonomous",
    "base_name": "builder",
    "goal": "Add a /health route and a test",
    "target_puller": "puller-01",
    "model": "qwen3.5:27b",
    "auto_start": true
  }'
```

`target_puller` here is the **LLM** puller (`puller-01`), not the
session inbox. The spawned instance copies `memory.md` and can take a
goal immediately.

## Session worker

`python -m node_agent.session_worker` (or `scripts/run-builder-worker.sh`)
heartbeats as puller `builder-01`, claims those session Tasks, runs
them with node_agent tools (including `run_command`), and sends LLM
turns to `puller-01`. Persistent memory lives in
`{agents_root}/builder-01/memory.md`.

```bash
cd agentnet-node
CONTROL_PLANE_URL=http://sg02:8000 ./scripts/run-builder-worker.sh
```

Safe to run alongside factory: it only consumes `builder-01`.
