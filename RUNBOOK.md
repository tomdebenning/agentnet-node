# Agentnet Node — Runbook

Operational guide for running a full **Agentnet** stack on one host: **control-plane**, **task-puller**, and **agentnet-node** (gateway + local agents).

---

## 1. What you are running

| Component | Repo | Role |
|-----------|------|------|
| **control-plane** | `control-plane/` | Central router + Redis queues + registry |
| **task-puller** | `task-puller/` | Pulls LLM work from control-plane, calls local Ollama |
| **agentnet-node** | `agentnet-node/` | Host gateway: agent lifecycle, admin UI, proxy to control-plane |
| **node_agent** | (inside agentnet-node) | Slim agent process spawned per agent directory |
| **Redis** | external | Queue + registry backing store for control-plane |
| **Ollama** | external | Local LLM runtime paired with task-puller |

Traffic flow for a chat turn:

```
Admin (browser/TUI) → gateway :8080
Agent (node_agent)  → gateway /proxy/* → control-plane :8000
Task-puller         → control-plane (fetch/respond)
Task-puller         → Ollama :11434
```

Agents **never** talk to control-plane directly. The gateway is the only outbound client for agent task/response/heartbeat traffic.

---

## 2. Prerequisites

- **Python 3.11+**
- **Redis** reachable (default `redis://localhost:6379/0`)
- **Ollama** running with at least one tool-capable model pulled
- **Node.js 18+** (only if building the React UI)
- Optional: **Brave Search API key** for the `web_search` tool

Recommended layout on disk:

```
/home/you/projects/
  control-plane/
  task-puller/
  agentnet-node/
```

---

## 3. First-time setup

Run once per machine (or once per clone).

### 3.1 Redis

```bash
# Example: local Redis
redis-server

# Verify
redis-cli ping
# → PONG
```

### 3.2 Control plane

```bash
cd control-plane
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cp config.example.yaml config.yaml
# Edit redis.url if needed

.venv/bin/python -m control_plane
# Listens on 0.0.0.0:8000 by default
```

Health check:

```bash
curl -sS http://127.0.0.1:8000/health
# {"status":"ok"}
```

### 3.3 Task puller + Ollama

```bash
# Pull a model (example)
ollama pull llama3.1:8b

cd task-puller
python3 -m venv .venv
.venv/bin/pip install -e .

cp config.example.yaml config.yaml
```

Edit `config.yaml`:

- `puller.name` — must match `default_target_puller` in agent configs (e.g. `puller-01`)
- `control_plane.url` — `http://127.0.0.1:8000`
- `ollama.url` — `http://localhost:11434`

```bash
.venv/bin/python -m task_puller
```

Verify puller registered:

```bash
curl -sS http://127.0.0.1:8000/pullers | python3 -m json.tool
```

### 3.4 Agentnet node (gateway)

```bash
cd agentnet-node
python3 -m venv .venv
.venv/bin/pip install -e .

cp config.example.yaml config.yaml
```

Edit `config.yaml`:

| Key | Purpose |
|-----|---------|
| `node.id` | Unique node ID in control-plane registry |
| `server.host` / `server.port` | Gateway bind (default `127.0.0.1:8080`) |
| `agents_root` | Where agent directories live (`./agents` dev, `/opt/agentnet/agents` prod) |
| `control_plane.url` | Control plane base URL |

Optional — Brave Search:

```bash
export BRAVE_SEARCH_API_KEY="your-key-here"
# or set brave_search.api_key in config.yaml
```

Build the web UI (served by gateway in production):

```bash
cd frontend
npm install
npm run build
cd ..
```

Start gateway:

```bash
.venv/bin/python -m gateway
```

Verify:

```bash
curl -sS http://127.0.0.1:8080/api/status | python3 -m json.tool
curl -sS http://127.0.0.1:8000/nodes | python3 -m json.tool
```

Open the web UI: [http://127.0.0.1:8080](http://127.0.0.1:8080)

---

## 4. Startup order

Start dependencies before dependents:

```
1. Redis
2. control-plane
3. task-puller (requires Ollama)
4. agentnet-node gateway
5. individual agents (via UI/API, or they start on demand)
```

Shutdown in reverse:

```
1. Stop agents (UI/API or gateway shutdown stops all)
2. agentnet-node gateway
3. task-puller
4. control-plane
5. Redis (optional last)
```

---

## 5. Creating and running an agent

### 5.1 Agent directory layout

Each agent is a directory under `{agents_root}/{agent-id}/`:

```
agents/my-agent/
  config.md      # YAML frontmatter: agent_id, puller, model, limits
  persona.md     # YAML frontmatter + persona/instructions body
  memory.md      # YAML frontmatter + persistent memory body
  workspace/     # sandboxed file tools
  databases/     # SQLite files (*.sqlite)
  agent_state.db # conversation history (created at runtime)
```

Example `config.md` frontmatter:

```yaml
---
agent_id: my-agent
default_target_puller: puller-01
default_model: llama3.1:8b
temperature: 0.7
num_ctx: 8192
max_rounds_per_conversation: 50
response_poll_interval_seconds: 2
response_timeout_seconds: 300
---
```

**Important:** `default_target_puller` must match a live puller's `puller.name`. `default_model` must be available on that puller's Ollama instance.

### 5.2 Web UI

1. Open [http://127.0.0.1:8080](http://127.0.0.1:8080)
2. **New agent** — set agent ID, target puller, model
3. Open the agent → edit **config**, **persona**, **memory** tabs → **Save**
4. **Start** / **Stop** as needed

### 5.3 Textual TUI

Gateway must be running:

```bash
cd agentnet-node
.venv/bin/python -m tui
# or: .venv/bin/python -m tui --api-url http://127.0.0.1:8080
```

| Key | Action |
|-----|--------|
| `c` | Create agent |
| `r` | Refresh list |
| Enter | Open agent detail |
| `s` | Start agent (detail screen) |
| `x` | Stop agent |
| `d` | Delete agent |
| `q` | Quit |

### 5.4 REST API (automation)

Base URL: `http://127.0.0.1:8080/api`

```bash
# List agents
curl -sS http://127.0.0.1:8080/api/agents

# Create agent
curl -sS -X POST http://127.0.0.1:8080/api/agents \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"research-01","target_puller":"puller-01","model":"llama3.1:8b"}'

# Read config.md
curl -sS http://127.0.0.1:8080/api/agents/research-01/files/config

# Write config.md (full raw file)
curl -sS -X PUT http://127.0.0.1:8080/api/agents/research-01/files/persona \
  -H 'Content-Type: application/json' \
  -d '{"content":"---\nname: Researcher\nrole: analyst\n---\n# Instructions\n..."}'

# Start / stop
curl -sS -X POST http://127.0.0.1:8080/api/agents/research-01/start
curl -sS -X POST http://127.0.0.1:8080/api/agents/research-01/stop

# Delete (stops first if running)
curl -sS -X DELETE http://127.0.0.1:8080/api/agents/research-01
```

### 5.5 Interactive agent REPL (debug)

Run an agent in the foreground with stdin attached:

```bash
cd agentnet-node
.venv/bin/python -m node_agent \
  --agent-dir ./agents/my-agent \
  --gateway-url http://127.0.0.1:8080
```

Type messages; Ctrl-D to exit. Useful for debugging persona/tools without the gateway spawn manager.

---

## 6. Health and observability

### Gateway

```bash
curl -sS http://127.0.0.1:8080/api/status
```

Returns `node_id`, `agent_count`, `running_agent_count`.

### Control plane

```bash
# Overall health
curl -sS http://127.0.0.1:8000/health

# Aggregate queue/registry stats
curl -sS http://127.0.0.1:8000/status | python3 -m json.tool

# Registered nodes, pullers, agents
curl -sS http://127.0.0.1:8000/nodes
curl -sS http://127.0.0.1:8000/pullers
curl -sS http://127.0.0.1:8000/agents

# Recent activity (no message bodies)
curl -sS "http://127.0.0.1:8000/activity?max=20"
```

### Optional TUIs (sibling repos)

```bash
# Control plane dashboard
cd control-plane && ./rund.sh -d

# Task puller dashboard
cd task-puller && ./rund.sh
```

### What “healthy” looks like

- `/health` → 200 on control-plane
- At least one puller in `/pullers` with `is_stale: false`
- Node appears in `/nodes` with recent heartbeat
- Agent in `/agents` after start (agent heartbeats via gateway proxy)
- Task queue drains: puller logs show fetch → Ollama → respond

---

## 7. Configuration reference

### Environment variables

| Variable | Component | Purpose |
|----------|-----------|---------|
| `CONTROL_PLANE_CONFIG` | control-plane | Path to config YAML |
| `TASK_PULLER_CONFIG` | task-puller | Path to config YAML |
| `AGENTNET_NODE_CONFIG` | agentnet-node | Path to gateway config YAML |
| `BRAVE_SEARCH_API_KEY` | agentnet-node | Brave Search API key (overrides YAML) |
| `AGENTNET_GATEWAY_URL` | node_agent | Gateway URL when spawned by manager |

### Production path defaults

| Setting | Dev | Production (recommended) |
|---------|-----|--------------------------|
| `agents_root` | `./agents` | `/opt/agentnet/agents` |
| Gateway bind | `127.0.0.1:8080` | `127.0.0.1:8080` (localhost only; v1 has no auth) |
| Control plane | `http://127.0.0.1:8000` | Your private-network URL |

---

## 8. Troubleshooting

### Gateway won't start — port in use

```bash
ss -tlnp | grep 8080
# Stop conflicting process or change server.port in config.yaml
```

### Agent stuck in `starting` / immediately `error`

Check gateway logs. Common causes:

- `config.md` missing or invalid frontmatter
- Agent directory deleted while process running

Inspect process exit:

```bash
curl -sS http://127.0.0.1:8080/api/agents/my-agent | python3 -m json.tool
# Look at process_state, return_code, error
```

Run foreground REPL (see §5.5) for stderr.

### Agent `waiting_for_llm` / response timeout

1. Confirm puller is running and registered:

   ```bash
   curl -sS http://127.0.0.1:8000/pullers
   ```

2. Confirm `default_target_puller` in agent `config.md` matches `puller.name` in task-puller config.

3. Confirm model exists on Ollama:

   ```bash
   curl -sS http://localhost:11434/api/tags
   ```

4. Check control-plane queues:

   ```bash
   curl -sS http://127.0.0.1:8000/queues
   curl -sS http://127.0.0.1:8000/status
   ```

5. Increase `response_timeout_seconds` in agent `config.md` for slow models.

### `web_search` tool fails

- Set `BRAVE_SEARCH_API_KEY` or `brave_search.api_key` in gateway config
- Agents call search through the gateway; the key is never stored in agent directories

### Node not in `/nodes`

- Gateway must be running (sends `POST /heartbeat/node` every 30s by default)
- Verify `control_plane.url` in gateway config
- Check control-plane logs for connection errors

### Schema / wire format errors after upgrades

`schemas.py` must be **byte-identical** in:

- `control-plane/src/control_plane/schemas.py`
- `task-puller/src/task_puller/schemas.py`
- `dagent-one/src/agent/schemas.py`
- `agentnet-node/src/gateway/schemas.py`

After changing schemas in one repo, copy to all four before restarting services.

### Purging stuck queues (operator)

```bash
# Purge puller task backlog
curl -sS -X DELETE http://127.0.0.1:8000/queues/puller/puller-01

# Purge agent response backlog
curl -sS -X DELETE http://127.0.0.1:8000/queues/agent/my-agent
```

**Warning:** purged items are lost permanently.

---

## 9. Production notes

### systemd (sketch)

Adjust paths and users for your environment.

**control-plane** — see `control-plane/README.md` sample unit.

**task-puller** — see `task-puller/README.md` sample unit.

**agentnet-node gateway** (example):

```ini
[Unit]
Description=Agentnet Node Gateway
After=network-online.target

[Service]
Type=simple
User=agentnet
WorkingDirectory=/opt/agentnet/agentnet-node
Environment=AGENTNET_NODE_CONFIG=/opt/agentnet/agentnet-node/config.yaml
Environment=BRAVE_SEARCH_API_KEY=...
ExecStart=/opt/agentnet/agentnet-node/.venv/bin/python -m gateway
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ensure `frontend/dist/` is built before relying on the web UI in production.

### Security (v1)

- Gateway binds to **localhost only** by default
- **No authentication** on gateway API or web UI in v1
- Do not expose port 8080 to untrusted networks without adding auth/reverse-proxy controls first
- Control plane is intended for **private networks** (see control-plane README auth TODOs)

### Backing up agents

Back up the entire agent directory:

```bash
tar -czf my-agent-backup.tgz -C /opt/agentnet/agents my-agent
```

Includes persona, memory, workspace, databases, and conversation state.

---

## 10. Quick reference — one-liner dev stack

In separate terminals:

```bash
# Terminal 1
redis-server

# Terminal 2
cd control-plane && .venv/bin/python -m control_plane

# Terminal 3
cd task-puller && .venv/bin/python -m task_puller

# Terminal 4
cd agentnet-node && .venv/bin/python -m gateway
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080), create an agent, edit persona, start it.

---

## 11. Related docs

- `agentnet-node/README.md` — project overview
- `control-plane/README.md` — control-plane API and operator endpoints
- `task-puller/README.md` — puller pools and Ollama pairing
- `dagent-one/README.md` — full agent template (alternative to slim `node_agent`)
