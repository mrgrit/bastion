#!/usr/bin/env bash
# §2.3 구현 — D: 타깃 상태-리셋 (full VM/LVM snapshot 대체).
# 사건 격리 표면: ① 타깃은 ephemeral(docker run --rm per task) ② SIEM 은 사건 타임윈도우로 격리(리셋 X)
#  ③ M3 차단룰은 fw 의 'inet eval_reset' 전용 테이블에만 → 리셋=그 테이블 삭제(production NAT 무손상)
#  ④ E.G/KG 는 조건 시작 시 seed 로 reset (reset_store_each_condition).
# 편차 명시(Runbook §0): literal snapshot/rollback 아님. 실 변경표면(nft 차단 + ephemeral 타깃)에 한정해
#  사건당 클린 baseline 을 달성. 무거운 stateful(wazuh/elastic/win)·host LVM 은 건드리지 않음(리스크 회피).
set -uo pipefail
SSH="sshpass -p 1 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
 -o ControlMaster=auto -o ControlPath=/tmp/cc6v6-%r@%h-%p -o ControlPersist=300s ccc@192.168.0.105"
HERE="$(cd "$(dirname "$0")/.." && pwd)"; BASE="$HERE/state/nft_baseline.txt"
FW="docker exec 6v6-fw"

case "${1:-}" in
  baseline)   # 1회: production nft 베이스라인 캡처 (감사용)
    $SSH "$FW nft list ruleset" 2>/dev/null | grep -v setlocale > "$BASE"
    echo "baseline captured: $(wc -l < "$BASE") lines → $BASE" ;;
  event-start)  # SIEM 타임윈도우 마커 (epoch). 측정코드가 [ts,now] 로 alert 격리.
    $SSH "date +%s" 2>/dev/null | grep -v setlocale ;;
  event-reset)  # 사건 종료 후: eval 차단테이블 제거 + dirty cctest 타깃 제거
    $SSH "$FW sh -c 'nft delete table inet eval_reset 2>/dev/null; true'
          docker ps -aq --filter name=cctest 2>/dev/null | xargs -r docker rm -f >/dev/null 2>&1; true" 2>&1 | grep -v setlocale
    echo "event-reset: eval_reset table cleared + cctest targets removed" ;;
  condition-reset)  # 조건 시작: bastion E.G/KG 를 seed 로 초기화 (reset_store). SEED 경로 인자.
    SEED="${2:?seed graph.db path required}"
    echo "condition-reset: restore E.G seed=$SEED (구현시 6v6_bastion-data/graph.db 교체 + bastion 재기동)"
    # 실행부(eval 가동 시 활성화): scp $SEED → 0.105, docker cp 로 graph.db 교체, bastion restart.
    ;;
  verify)  # §2.3 왕복 검증: 차단룰 add → reset → gone + production 보존
    $SSH "$FW sh -c '
      nft add table inet eval_reset 2>/dev/null; nft add chain inet eval_reset block 2>/dev/null
      nft add rule inet eval_reset block ip saddr 203.0.113.66 drop 2>/dev/null
      A=\$(nft list table inet eval_reset 2>/dev/null | grep -c 203.0.113.66)
      nft delete table inet eval_reset 2>/dev/null
      G=\$(nft list table inet eval_reset 2>/dev/null | grep -c 203.0.113.66)
      NAT=\$(nft list tables | grep -c \"table ip nat\")
      echo \"added=\$A reset_remaining=\$G nat_preserved=\$NAT\"
      [ \$A -eq 1 ] && [ \$G -eq 0 ] && [ \$NAT -ge 1 ] && echo ROUNDTRIP_PASS || echo ROUNDTRIP_FAIL'" 2>&1 | grep -v setlocale ;;
  *) echo "usage: $0 {baseline|event-start|event-reset|condition-reset <seed>|verify}"; exit 2 ;;
esac
