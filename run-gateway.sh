#!/usr/bin/env bash
# Start the agentnet-node gateway (FastAPI + optional built SPA).
# Loads .env from the repo root if present.
#
# Typical .env variables:
#   AGENTNET_NODE_CONFIG=/path/to/config.yaml
#   BRAVE_SEARCH_API_KEY=...
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
  echo "run-gateway.sh: no Python interpreter found." >&2
  echo "  Create a venv: python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 127
fi

if ! "${PY}" -c "import gateway" 2>/dev/null; then
  echo "run-gateway.sh: gateway is not installed for ${PY}" >&2
  echo "run-gateway.sh: from ${ROOT}, run: python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

exec "${PY}" -m gateway "$@"
