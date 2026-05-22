#!/usr/bin/env bash
# Start the Textual TUI for the agentnet-node gateway admin API.
# The gateway must already be running (default http://127.0.0.1:8080).
#
# Typical .env variables:
#   AGENTNET_GATEWAY_API_URL=http://127.0.0.1:8080
#   AGENTNET_NODE_PYTHON=/path/to/python  (optional override)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi

if [[ -n "${AGENTNET_NODE_PYTHON:-}" ]]; then
  PY="${AGENTNET_NODE_PYTHON}"
elif [[ -n "${PYTHON:-}" ]]; then
  PY="${PYTHON}"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "run-tui.sh: no Python interpreter found." >&2
  echo "  Create a venv: python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 127
fi

if ! "${PY}" -c "import tui" 2>/dev/null; then
  echo "run-tui.sh: tui is not installed for ${PY}" >&2
  echo "run-tui.sh: from ${ROOT}, run: python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

API_URL="${AGENTNET_GATEWAY_API_URL:-http://127.0.0.1:8080}"
exec "${PY}" -m tui --api-url "${API_URL}" "$@"
