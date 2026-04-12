#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
INSTALL_DIR="$(pwd)"

echo "=== Bastion Setup ==="
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt -q

[ "$(hostname)" != "bastion" ] && sudo hostnamectl set-hostname bastion 2>/dev/null || true
[ ! -f .env ] && cp .env.example .env 2>/dev/null && echo ".env 생성됨" || echo ".env 존재"

# ── systemd 서비스 설치 (API 자동 시작) ────────────────────────────────────
if command -v systemctl &>/dev/null; then
    SERVICE_FILE="/etc/systemd/system/bastion-api.service"
    sed "s|/opt/bastion|${INSTALL_DIR}|g" bastion-api.service | sudo tee "$SERVICE_FILE" > /dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable bastion-api
    sudo systemctl restart bastion-api
    echo "API 서비스 시작됨 → http://localhost:8003"
fi

echo "=== 완료. ./bastion.sh 로 TUI 실행 ==="
