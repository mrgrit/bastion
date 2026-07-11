#!/usr/bin/env bash
# 한 과제를 bastion 에 1회 발제 → 완료까지 폴링 → ndjson 을 stdout 으로 출력.
# 순차 전용(한 번에 하나). 진행로그는 stderr, 결과 ndjson 은 stdout.
# 사용: run_task.sh <RUN_ID> <MESSAGE_B64> [MAX_POLLS=34]
set -uo pipefail
TID="$1"; B64="$2"; MAXP="${3:-34}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# .eval-secrets 로드 (EL34_HOST/USER/PASS)
set -a; . "$HERE/../../.eval-secrets"; set +a
H="$EL34_HOST"; PW="$EL34_PASS"; U="${EL34_USER:-ccc}"
SSH="sshpass -p $PW ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 $U@$H"
OUT="/tmp/${TID}.out"; REQ="/tmp/${TID}.req.json"
clean(){ grep -viE 'setlocale|warning|^\[sudo\]|password for'; }

echo "[$TID] issue @ $(date +%T)" >&2
$SSH "echo '$B64' | base64 -d > $REQ
echo $PW | sudo -S -p '' docker cp $REQ el34-bastion:$REQ 2>/dev/null
echo $PW | sudo -S -p '' docker exec el34-bastion rm -f $OUT 2>/dev/null
echo $PW | sudo -S -p '' docker exec -d el34-bastion sh -c 'curl -s -N --max-time 1800 -X POST localhost:9100/chat -H Content-Type:application/json -d @$REQ > $OUT 2>&1'
echo launched" 2>&1 | clean >&2

prev=-1; stable=0
for i in $(seq 1 "$MAXP"); do
  info=$($SSH "echo $PW | sudo -S -p '' docker exec el34-bastion sh -c 'pgrep -f 9100/chat >/dev/null && echo RUN || echo DONE; wc -c < $OUT 2>/dev/null; tail -c 600 $OUT 2>/dev/null | grep -q kg_status && echo TERM || echo NO'" 2>/dev/null | clean)
  st=$(printf '%s\n' "$info" | sed -n 1p); cur=$(printf '%s\n' "$info" | sed -n 2p); term=$(printf '%s\n' "$info" | sed -n 3p)
  echo "[$TID poll $i @ $(date +%T)] ${st:-?} bytes=${cur:-0} ${term:-?}" >&2
  [ "$st" = DONE ] && break
  [ "$term" = TERM ] && { echo "[$TID terminal(kg_status) → done @ $(date +%T)]" >&2; break; }
  # 긴 정체(180s, gpt-oss 사고정지보다 김) → 폴백 종료
  if [ "${cur:-0}" -gt 100 ] && [ "$cur" = "$prev" ]; then stable=$((stable+1)); else stable=0; fi
  [ "$stable" -ge 9 ] && { echo "[$TID long-idle 180s → done @ $(date +%T)]" >&2; break; }
  prev=$cur
  sleep 20
done
# 결과 ndjson → stdout
$SSH "echo $PW | sudo -S -p '' docker exec el34-bastion cat $OUT" 2>/dev/null | clean
