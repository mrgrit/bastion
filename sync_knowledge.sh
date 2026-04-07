#!/usr/bin/env bash
# CCC 서버에서 교육 콘텐츠를 bastion의 knowledge/ 디렉토리로 동기화
# CCC 서버에서 실행: bash sync_knowledge.sh <bastion_ip> <ssh_user> <ssh_password>
set -euo pipefail

BASTION_IP="${1:-10.20.30.200}"
SSH_USER="${2:-ccc}"
SSH_PASS="${3:-1}"
CCC_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd || echo /home/ccc/ccc)"
DEST="/opt/bastion/knowledge"

echo "=== Syncing knowledge to bastion ($BASTION_IP) ==="

# 교안 + 실습을 tar로 묶어서 전송
echo "[1/3] Packaging content..."
cd "$CCC_DIR"
tar czf /tmp/ccc-knowledge.tar.gz \
    contents/education/ \
    contents/labs/*-nonai/ \
    --exclude='__pycache__' 2>/dev/null

echo "[2/3] Uploading to bastion..."
sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no \
    /tmp/ccc-knowledge.tar.gz "$SSH_USER@$BASTION_IP:/tmp/"

echo "[3/3] Extracting on bastion..."
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$SSH_USER@$BASTION_IP" \
    "echo '$SSH_PASS' | sudo -S bash -c 'mkdir -p $DEST && tar xzf /tmp/ccc-knowledge.tar.gz -C $DEST --strip-components=1 && rm /tmp/ccc-knowledge.tar.gz && echo \"Knowledge synced: \$(find $DEST -type f | wc -l) files\"'"

rm -f /tmp/ccc-knowledge.tar.gz
echo "=== Done ==="
