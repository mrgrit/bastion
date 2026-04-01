# 2단계 제안서: 프롬프트 엔지니어링 적용

## 현재 문제

OpsClaw의 프롬프트 내용이 선언적 규칙 위주로, Claude Code에서 검증된 구체적 패턴들이 부족하다.

| 측면 | OpsClaw 현재 | Claude Code 패턴 |
|------|-------------|-----------------|
| 규칙 표현 | "SubAgent 직접 호출 금지" | "모든 명령은 Manager API의 /dispatch를 통해 전달한다" |
| 도구 가이드 | 없음 | "Read 대신 cat 사용 금지, Edit 대신 sed 사용 금지" |
| 출력 효율성 | 없음 | "결론 먼저, 1문장이면 3문장 쓰지 마라" |
| 안전 예시 | 표만 존재 | "rm -rf, DROP TABLE, force-push 등 구체적 목록" |
| JSON 출력 | "Respond ONLY with JSON" | 성공/실패/완료 3가지 예시 포함 |
| 위험 행동 | risk_level 표 | "reversibility와 blast radius를 고려하라" |

## 목표

Claude Code `prompts.ts`의 베스트 프랙티스 6가지를 OpsClaw 프롬프트에 적용한다. 코드 변경 최소, 프롬프트 텍스트 변경 위주.

## 적용 패턴 6가지

### A. 역할+제약+도구를 분리된 섹션으로

**Claude Code 원본** (`getSimpleIntroSection`, `getSimpleSystemSection`, `getSimpleDoingTasksSection` 등 7개 함수):
```
# System (도구, 권한, 태그)
# Doing tasks (코딩 규범, 보안)
# Executing actions with care (위험 행동)
# Using your tools (도구별 가이드)
# Tone and style
# Output efficiency
```

**OpsClaw 적용 (`prompt_engine/sections/`):**
```
# Identity (역할 정의)
# Workflow (작업 순서, stage 전이)
# Safety (risk_level, 안전 규칙)
# Tools (사용 가능한 도구, 사용법)
# Environment (인프라 매핑)
# Output (보고서 형식, 효율성)
```

### B. "하지 마라" → "이렇게 하라" 변환

**현재:**
```
- SubAgent에 직접 POST 금지
- 파괴적 명령은 사용자 확인 후에만 실행
```

**개선:**
```
- 모든 명령은 반드시 Manager API의 /dispatch 또는 /execute-plan을 통해 전달한다.
  Manager가 evidence를 자동 기록하고 PoW 블록을 생성한다.
- 파괴적 명령(rm -rf, DROP TABLE, fdisk 등)은 다음 절차를 따른다:
  1. execute-plan에 risk_level="critical"로 포함
  2. 시스템이 자동으로 dry_run 강제
  3. dry_run 결과를 사용자에게 보여주고 확인 요청
  4. confirmed=true로 재실행
```

### C. 도구별 사용 가이드

**Claude Code 원본** (`getUsingYourToolsSection`, 라인 269-314):
```
Do NOT use Bash to run commands when a relevant dedicated tool is provided:
 - To read files use Read instead of cat, head, tail
 - To edit files use Edit instead of sed or awk
 - To search for files use Glob instead of find or ls
```

**OpsClaw 적용:**
```
명령 실행 방법을 선택할 때:
 - 상태 확인 1개 명령 → dispatch (mode=shell)
   예: systemctl status nginx, df -h, cat /etc/os-release
 - 다단계 작업 계획 → execute-plan (tasks 배열)
   예: 서버 점검, 패키지 설치, 보안 감사
 - 등록된 표준 절차 → playbook/run
   예: nightly_health_baseline_check, diagnose_web_latency
 - dispatch mode=auto는 LLM 변환 정확도가 보장되지 않으므로 프로덕션에서 사용하지 않는다.
```

### D. 출력 효율성 지시

**Claude Code 원본** (`getOutputEfficiencySection`, 라인 403-428):
```
IMPORTANT: Go straight to the point. Try the simplest approach first.
Lead with the answer or action, not the reasoning.
Skip filler words, preamble, and unnecessary transitions.
If you can say it in one sentence, don't use three.
```

**OpsClaw 적용:**
```
# Output Rules

completion-report 작성 시:
- summary: 1문장. 결론 먼저, 근거 나중.
- work_details: 실행된 명령과 exit code만. 설명 불필요.
- issues: 실패/이상만 기록. 추측이나 부연 금지.
- next_steps: 구체적 행동만. "모니터링 필요" 같은 모호한 표현 금지.

evidence 해석 시:
- exit_code=0이면 성공으로 판단. stdout 내용을 재해석하지 않는다.
- exit_code≠0이면 stderr를 확인하고 원인을 1문장으로 요약한다.
- success_rate < 1.0이면 실패한 evidence의 stderr만 보고한다.
```

### E. 안전 행동의 구체적 예시

**Claude Code 원본** (`getActionsSection`, 라인 255-267):
```
Examples of risky actions that warrant user confirmation:
- Destructive operations: deleting files/branches, dropping database tables, killing processes, rm -rf
- Hard-to-reverse operations: force-pushing, git reset --hard, amending published commits
- Actions visible to others: pushing code, creating PRs, sending messages
```

**OpsClaw 적용:**
```
# Risk Assessment Examples

위험 행동 판단 기준 — reversibility(되돌릴 수 있는가)와 blast radius(영향 범위):

파괴적 (항상 사용자 확인):
  rm -rf, DROP TABLE, fdisk, 인증서 삭제, iptables -F, systemctl mask

되돌리기 어려움 (dry_run 먼저):
  apt-get remove, systemctl disable, 설정 파일 덮어쓰기, DB 스키마 변경

다른 시스템에 영향:
  방화벽 규칙 변경 (secu), WAF 설정 변경 (web), SIEM 규칙 수정 (siem)
  → 반드시 대상 서버의 SubAgent URL을 명시하고, 변경 전 현재 상태를 먼저 수집

안전 (자유롭게 실행):
  df -h, free -m, systemctl status, cat, ls, ps aux, netstat/ss
```

### F. JSON 출력 강제 시 예시 포함

**현재 (mission 프롬프트):**
```
Respond ONLY with JSON:
{"action":"what you plan to do","command":"bash command","done":false}
```

**개선:**
```
Each turn, respond with ONLY a JSON object. No markdown, no explanation.

Example 1 — Execute a command:
{"action":"check disk usage","command":"df -h","done":false}

Example 2 — Handle error and retry:
{"action":"retry with sudo","command":"echo 1 | sudo -S df -h","done":false}

Example 3 — Mission complete:
{"action":"done","command":"","done":true,"summary":"Disk usage normal at 45% on /dev/sda1"}

Example 4 — Cannot proceed:
{"action":"blocked","command":"","done":true,"summary":"Target port 8080 is closed, cannot reach JuiceShop"}
```

## 영향 파일 (OpsClaw 기준)

| 파일 | 변경 내용 |
|------|----------|
| `packages/prompt_engine/sections/safety.py` | 패턴 B, E 적용 |
| `packages/prompt_engine/sections/tools.py` | 패턴 C 적용 |
| `packages/prompt_engine/sections/output.py` | 패턴 D 적용 |
| `packages/prompt_engine/sections/workflow.py` | 패턴 A, B 적용 |
| `apps/subagent-runtime/src/main.py:363-404` | 패턴 F 적용 (mission JSON 예시) |
| `apps/subagent-runtime/src/main.py:524-536` | 패턴 F 적용 (explore JSON 예시) |
| `apps/subagent-runtime/src/main.py:669-674` | 패턴 F 적용 (daemon JSON 예시) |

## 구현 계획

1. prompt_engine 섹션에 패턴 A~E 내용 반영 (1단계와 동시 진행)
2. subagent-runtime의 mission/explore/daemon 프롬프트에 패턴 F 적용
3. Before/After 비교: 동일 미션 목표에 대한 LLM 행동 비교

## 검증 방법

1. mission 실행: "디스크 사용량 점검" → JSON 파싱 성공률 비교
2. execute-plan: "nginx 설치 후 상태 확인" → task 구성 품질 비교
3. completion-report: 동일 evidence에 대한 보고서 품질 비교
4. daemon: 이상 감지 시 severity 판단 정확도 비교
