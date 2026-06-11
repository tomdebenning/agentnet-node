#!/usr/bin/env bash
# Start the Textual TUI (connects to the gateway API).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi

export PATH="${HOME}/.local/bin:${PATH}"

API_URL="${AGENTNET_GATEWAY_API_URL:-http://127.0.0.1:8080}"

if command -v curl >/dev/null 2>&1; then
  if ! curl -sf "${API_URL}/api/status" >/dev/null 2>&1; then
    echo "run-tui.sh: WARNING — gateway not reachable at ${API_URL}" >&2
    echo "run-tui.sh: Start it in another terminal: ./run-gateway.sh" >&2
    echo "run-tui.sh: Press r in the TUI to refresh once the gateway is up." >&2
    echo >&2
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv sync --quiet
  exec uv run agentnet-tui --api-url "${API_URL}" "$@"
fi

PY="${AGENTNET_NODE_PYTHON:-${PYTHON:-}}"
if [[ -z "${PY}" ]]; then
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PY="${ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
  else
    echo "run-tui.sh: install uv (https://docs.astral.sh/uv/) or set PYTHON" >&2
    exit 127
  fi
fi

if ! "${PY}" -c "import tui" 2>/dev/null; then
  echo "run-tui.sh: run 'uv sync' from ${ROOT} to install workspace packages" >&2
  exit 1
fi

exec "${PY}" -m tui --api-url "${API_URL}" "$@"
