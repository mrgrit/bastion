# Bastion — AI Agent 작업 가이드

이 프로젝트는 Claude Code 소스코드(`src/`)를 분석하여 OpsClaw 개선 방향을 도출하고, 구체적인 설계 산출물을 만드는 프로젝트다.

## 핵심 원칙

1. `src/`는 읽기 전용 레퍼런스다. 수정하지 않는다.
2. 분석 결과는 `docs/analysis/`에, 적용 제안은 `docs/proposals/`에 작성한다.
3. OpsClaw에 실제 적용할 코드는 이 레포가 아닌 OpsClaw 레포(`~/opsclaw/opsclaw/`)에 작성한다.
4. 모든 커뮤니케이션은 한국어로 한다.

## 분석 방법

`src/` 탐색 시:
- `src/constants/prompts.ts` — 시스템 프롬프트 조합 로직 (최우선 분석)
- `src/Tool.ts` — 도구 인터페이스 정의
- `src/tools/` — 60+ 도구 구현체
- `src/hooks/` — Hook 이벤트 시스템
- `src/state/` — 상태 관리 패턴
- `src/utils/model/` — 모델 관리
- `src/memdir/` — 메모리 시스템
- `src/skills/` — 스킬 로딩/실행

## 산출물 형식

### 분석 문서 (docs/analysis/)
```markdown
# [영역] 아키텍처 분석

## 핵심 발견
- 발견 사항 요약

## 코드 구조
- 파일 경로, 라인 번호, 핵심 패턴

## OpsClaw 현재 상태 vs Claude Code
- 비교 표

## 적용 가능 패턴
- 구체적 패턴 + 근거
```

### 제안서 (docs/proposals/)
```markdown
# [단계] 제안서

## 현재 문제
## 목표
## 설계
## 영향 파일 (OpsClaw 기준)
## 구현 계획
## 검증 방법
```

## OpsClaw 레퍼런스

- OpsClaw 경로: `/home/opsclaw/opsclaw/`
- Manager API: `apps/manager-api/src/main.py` (2,619줄)
- SubAgent: `apps/subagent-runtime/src/main.py` (800줄)
- Master Service: `apps/master-service/src/main.py` (292줄)
- pi_adapter: `packages/pi_adapter/runtime/client.py` (295줄)
- 프롬프트 문서: `docs/agent-system-prompt.md` (214줄)
