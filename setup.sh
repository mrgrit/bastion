#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "=== Bastion Setup ==="
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt -q
[ "$(hostname)" != "bastion" ] && sudo hostnamectl set-hostname bastion 2>/dev/null || true
[ ! -f .env ] && cp .env.example .env 2>/dev/null && echo ".env 생성됨" || echo ".env 존재"
echo "=== 완료. ./bastion.sh 로 실행 ==="
