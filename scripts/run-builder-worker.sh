#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://sg02:8000}"
export BUILDER_PULLER_NAME="${BUILDER_PULLER_NAME:-builder-01}"
export LLM_TARGET_PULLER="${LLM_TARGET_PULLER:-puller-01}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m node_agent.session_worker "$@"
fi
exec python3 -m node_agent.session_worker "$@"
