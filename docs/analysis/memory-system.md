# Claude Code 메모리 시스템 분석

## 핵심 발견

Claude Code의 메모리(`src/memdir/`)는 **파일 기반 영구 저장**으로, MEMORY.md 인덱스 + 개별 메모리 파일 구조. 200줄/25KB 용량 제한과 "저장하지 않을 것" 규칙이 핵심.

## 코드 구조

### 메모리 구조

```
~/.claude/projects/{project}/memory/
├── MEMORY.md          # 인덱스 (200줄 제한)
├── user_role.md       # 사용자 정보
├── feedback_testing.md # 피드백
└── project_auth.md    # 프로젝트 정보
```

### 메모리 유형

| 유형 | 목적 | 저장 시점 |
|------|------|----------|
| user | 사용자 역할/선호/지식 | 사용자 정보 파악 시 |
| feedback | 작업 방식 피드백 (교정+확인) | 사용자가 교정하거나 확인할 때 |
| project | 진행 중인 작업/목표/기한 | 프로젝트 상태 변경 시 |
| reference | 외부 시스템 위치 정보 | 외부 리소스 언급 시 |

### 용량 제한 (`src/memdir/memdir.ts`)

- 줄 수 제한: 200줄
- 바이트 제한: 25,000바이트
- 잘림 전략: 줄 먼저, 그 다음 바이트 경계

### "저장하지 않을 것"

- 코드 패턴/구조 (코드에서 직접 읽으면 됨)
- Git 히스토리 (git log/blame이 정확)
- 디버깅 해법 (수정은 코드에, 컨텍스트는 커밋 메시지에)
- CLAUDE.md에 이미 있는 내용
- 임시 작업 상태

### 자동 메모리 추출

대화에서 중요 정보를 감지 → 적절한 유형으로 자동 저장. 상대 날짜("목요일")는 절대 날짜("2026-03-05")로 변환.

## OpsClaw 적용 포인트

| Claude Code | OpsClaw 현재 | 개선 방향 |
|------------|-------------|----------|
| 4가지 메모리 유형 | category 필드만 | incident/runbook/failure/config 유형 |
| 200줄 용량 제한 | 없음 | LRU 기반 max_entries |
| 자동 추출 | auto_promote_high_reward만 | 프로젝트 완료 시 패턴 자동 추출 |
| "저장 금지" 규칙 | 없음 | stdout 원문, 임시 상태 제외 |
| 시맨틱 검색 | FTS만 | Ollama embedding 추가 |
