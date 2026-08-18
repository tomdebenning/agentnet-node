# agentnet-node

Host-level gateway for **Agentnet**: manages local agents, proxies all control-plane traffic, and provides a **React web UI** plus a **Textual TUI** for agent lifecycle and Markdown file editing.

## Architecture

```
  React SPA / Textual TUI
           │
           ▼
  agent-node-gateway (127.0.0.1:8080)
     │                │
     │ spawn/stop     │ proxy tasks/responses/heartbeats
     ▼                ▼
  node_agent      control-plane
  (per agent)         │
                      ▼
                 task-puller + Ollama
```

Each agent lives in `{agents_root}/{agent-id}/` with Markdown files:

- `config.md` — YAML frontmatter + body
- `persona.md`
- `memory.md`
- `workspace/`
- `databases/`

## Quick start

```bash
# Gateway
cd agentnet-node
pip install -e .
cp config.example.yaml config.yaml
python3 -m gateway

# Web UI (dev)
cd frontend && npm install && npm run dev

# Web UI (production — served from gateway)
cd frontend && npm run build
python3 -m gateway

# TUI (gateway must be running)
python3 -m tui
```

## Requirements

- Python 3.11+
- Running [control-plane](../control-plane) (with node registry support)
- At least one [task-puller](../task-puller) for LLM work
- Optional: `BRAVE_SEARCH_API_KEY` for web search tool

## Sibling repositories

- **control-plane** — central router (extended with `/heartbeat/node`, `/nodes`)
- **task-puller** — Ollama worker
- **dagent-one** — full agent template (this project uses a new slim `node_agent` runtime)

Shared `schemas.py` must remain byte-identical across control-plane, task-puller, dagent-one, and `agentnet-node/src/gateway/schemas.py`.

## Builder (software worker)

`definitions/builder` is a spawnable software-builder with persistent
`memory.md` and a workspace-sandboxed `run_command` tool. It is not a
newsroom desk.

Chief of Staff creates work with `POST /sessions` and
`target_puller: "builder-01"` (or `definition: "builder"`). A running
`python -m node_agent.session_worker` picks those sessions up. Details:
[docs/BUILDER.md](docs/BUILDER.md).
