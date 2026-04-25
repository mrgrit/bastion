#!/usr/bin/env bash
# Bastion 업그레이드 — repo 에서 최신 코드 가져오기 + 의존성 갱신 + 서비스 재시작
# .env / .venv 보존. 사용: cd /opt/bastion && ./upgrade.sh
set -euo pipefail
cd "$(dirname "$0")"
INSTALL_DIR="$(pwd)"

echo "=== Bastion Upgrade ($(date -Iseconds)) ==="

# 1. 현재 버전 기록
OLD_REV=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
echo "[1/5] 현재 리비전: $OLD_REV"

# 2. 코드 업데이트 (로컬 변경 보존)
echo "[2/5] git pull (로컬 .env 보존)..."
git stash --include-untracked --quiet 2>/dev/null || true
if git pull --ff-only origin main; then
    NEW_REV=$(git rev-parse --short HEAD)
    echo "  $OLD_REV → $NEW_REV"
else
    echo "  ✗ git pull 실패 (네트워크/권한 확인)"
    git stash pop --quiet 2>/dev/null || true
    exit 1
fi
git stash pop --quiet 2>/dev/null || true

# 3. 의존성 갱신
echo "[3/5] requirements 갱신..."
if [ -f .venv/bin/activate ]; then
    .venv/bin/pip install -r requirements.txt -q
    echo "  ✓"
else
    echo "  ✗ .venv 없음 — ./setup.sh 먼저 실행"
    exit 1
fi

# 4. 서비스 재시작 (systemd → 그게 없으면 nohup 로 떠있는 process kill·재기동)
echo "[4/5] 서비스 재시작..."
if systemctl list-unit-files 2>/dev/null | grep -q '^bastion-api'; then
    if sudo -n true 2>/dev/null; then
        sudo systemctl restart bastion-api && echo "  ✓ systemctl restart bastion-api"
    else
        echo "  ⓘ systemd 서비스 있지만 sudo 필요 — 수동 실행: sudo systemctl restart bastion-api"
    fi
else
    # nohup 모드 — 기존 프로세스 kill·재시동
    OLD_PID=$(pgrep -f "python3 -m apps.bastion\|uvicorn api:app" | head -1 || true)
    if [ -n "$OLD_PID" ]; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
    set -a; [ -f .env ] && . ./.env; set +a
    nohup ./.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8003 > /tmp/bastion_api.log 2>&1 &
    disown
    sleep 3
    NEW_PID=$(pgrep -f "uvicorn api:app" | head -1 || true)
    if [ -n "$NEW_PID" ]; then
        echo "  ✓ uvicorn 재시작 (PID $NEW_PID)"
    else
        echo "  ✗ 재시작 실패 — tail /tmp/bastion_api.log"
    fi
fi

# 5. 헬스체크
echo "[5/5] 헬스체크..."
sleep 2
if curl -fsS --max-time 5 http://localhost:8003/health > /tmp/bastion_health.json 2>/dev/null; then
    MODEL=$(python3 -c "import json; d=json.load(open('/tmp/bastion_health.json')); print(d.get('model','?'))" 2>/dev/null || echo ?)
    SKILLS=$(python3 -c "import json; d=json.load(open('/tmp/bastion_health.json')); print(d.get('skills','?'))" 2>/dev/null || echo ?)
    echo "  ✓ API 정상 — model=$MODEL skills=$SKILLS"
else
    echo "  ✗ API 응답 없음 — tail /tmp/bastion_api.log"
    exit 1
fi

echo ""
echo "=== Upgrade 완료: $OLD_REV → $NEW_REV ==="
