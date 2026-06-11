#!/usr/bin/env bash
# Start the agentnet gateway (FastAPI API + built web UI).
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

ensure_web_built() {
  local web="${ROOT}/web"
  [[ -f "${web}/package.json" ]] || return 0
  if [[ "${AGENTNET_SKIP_FRONTEND_BUILD:-}" == "1" ]]; then
    return 0
  fi

  local dist_index="${web}/dist/index.html"
  local needs_build=0
  if [[ ! -f "${dist_index}" ]]; then
    needs_build=1
  else
    local script_path=""
    script_path="$(grep -oE 'src="/assets/[^"]+"' "${dist_index}" | head -1 | sed 's/src="//;s/"$//' || true)"
    if [[ -z "${script_path}" || ! -f "${web}/dist${script_path}" ]]; then
      needs_build=1
      echo "run-gateway.sh: web build is stale (missing JS bundle), rebuilding..." >&2
    fi
  fi

  if [[ "${needs_build}" -eq 0 ]]; then
    return 0
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "run-gateway.sh: npm not found — build manually: cd web && npm install && npm run build" >&2
    return 0
  fi

  echo "run-gateway.sh: building web UI..." >&2
  if [[ ! -d "${web}/node_modules" ]]; then
    echo "run-web.sh: installing web dependencies..." >&2
    (cd "${web}" && npm install)
  fi
  (cd "${web}" && npm run build)
}

ensure_web_built

if command -v uv >/dev/null 2>&1; then
  uv sync --quiet
  exec uv run agentnet-gateway "$@"
fi

PY="${AGENTNET_NODE_PYTHON:-${PYTHON:-}}"
if [[ -z "${PY}" ]]; then
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PY="${ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
  else
    echo "run-gateway.sh: install uv (https://docs.astral.sh/uv/) or set PYTHON" >&2
    exit 127
  fi
fi

if ! "${PY}" -c "import gateway" 2>/dev/null; then
  echo "run-gateway.sh: run 'uv sync' from ${ROOT} to install workspace packages" >&2
  exit 1
fi

exec "${PY}" -m gateway "$@"
