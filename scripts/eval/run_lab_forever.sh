#!/usr/bin/env bash
# 랩 전수 무인 실행 래퍼 — lab_loop 이 죽거나 끝나면 자동 재시작(ledger 재개).
# 2072 스텝 전량 완료 시에만 종료. 며칠 무인 운영용.
cd /home/ccc/bastion || exit 1
LOG=eval-tw2/lab_loop.log
TOTAL=2072
while true; do
  echo "[$(date '+%F %T')] lab_loop 시작" >> "$LOG"
  python3 scripts/eval/lab_loop.py >> "$LOG" 2>&1
  rc=$?
  done=$(python3 -c "import json;print(len(json.load(open('eval-tw2/lab_ledger.json')).get('steps',{})))" 2>/dev/null || echo 0)
  echo "[$(date '+%F %T')] lab_loop 종료 rc=$rc done=${done}/$TOTAL" >> "$LOG"
  if [ "${done:-0}" -ge "$TOTAL" ]; then
    echo "[$(date '+%F %T')] 전량 완료 → 래퍼 종료" >> "$LOG"; break
  fi
  sleep 60
done
