#!/usr/bin/env bash
# One-command demo: dashboard, seed PRs, then agent PRs. Ctrl-C stops the API.
set -euo pipefail
set -m
cd "$(dirname "$0")/.."

reset=1
for arg in "$@"; do
  if [[ "$arg" == "--no-reset" ]]; then
    reset=0
  else
    echo "unknown argument: $arg" >&2
    exit 2
  fi
done

if command -v uv >/dev/null 2>&1; then
  run() { uv run "$@"; }
else
  run() { "$@"; }
fi

api_pid=""
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$api_pid" ]]; then
    kill -- "-$api_pid" 2>/dev/null || kill "$api_pid" 2>/dev/null || true
    wait "$api_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

run uvicorn factory.api:app --port 8000 >/tmp/muscle-memory-api.log 2>&1 &
api_pid=$!

ready=0
for _ in $(seq 1 50); do
  if ! kill -0 "$api_pid" 2>/dev/null; then
    echo "factory api exited" >&2
    exit 1
  fi
  if curl -sf -o /dev/null http://127.0.0.1:8000/api/state; then
    ready=1
    break
  fi
  sleep 0.2
done
if [[ "$ready" -ne 1 ]]; then
  echo "factory api did not start on port 8000" >&2
  exit 1
fi

if command -v open >/dev/null 2>&1; then
  open http://localhost:8000 >/dev/null 2>&1 &
  disown || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:8000 >/dev/null 2>&1 &
  disown || true
else
  echo "http://localhost:8000"
fi

if [[ "$reset" -eq 1 ]]; then
  run python -m factory.run --prs data/seed --reset --pace 0.6
else
  run python -m factory.run --prs data/seed --pace 0.6
fi
run python -m factory.run --prs data/prs --pace 0.3
