#!/usr/bin/env bash
# deploy-bastion.sh — bastion 배포
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[bastion] Stopping..."
fuser -k 9000/tcp 2>/dev/null || true
sleep 1

echo "[bastion] Building UI..."
cd apps/bastion-ui && npm install --silent && npm run build && cd ../..

echo "[bastion] Starting bastion-api on :9000..."
set -a && [ -f .env ] && source .env; set +a
export PYTHONPATH="$(pwd)"
export DATABASE_URL="${DATABASE_URL:-postgresql://opsclaw:opsclaw@127.0.0.1:5432/bastion}"
export BASTION_API_KEY="${BASTION_API_KEY:-bastion-api-key-2026}"
nohup python3.11 -m uvicorn apps.bastion-api.src.main:app \
  --host 0.0.0.0 --port 9000 --log-level warning > /tmp/bastion.log 2>&1 &

sleep 2
curl -s http://localhost:9000/health && echo " [OK]"
