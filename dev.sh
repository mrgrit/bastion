#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

set -a; [ -f .env ] && source .env; set +a
export PYTHONPATH="$(pwd)"

case "${1:-api}" in
  api)
    echo "[bastion] Starting bastion-api on :9000..."
    python -m uvicorn apps.bastion-api.src.main:app --host 0.0.0.0 --port 9000 --reload
    ;;
  *)
    echo "Usage: ./dev.sh [api]"
    ;;
esac
