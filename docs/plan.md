# Bastion 전체 개선 계획

> Claude Code 아키텍처를 벤치마크하여 OpsClaw의 에이전트 지능 계층을 개선한다.

## 7대 개선 영역

### 1단계: 시스템 프롬프트 아키텍처 (영향도: 극대)

**문제**: OpsClaw의 LLM 시스템 프롬프트가 3줄 고정 문자열. 풍부한 문서(`agent-system-prompt.md`)가 런타임에 활용되지 않음.

**Claude Code 패턴**: `constants/prompts.ts`에서 14개 독립 섹션을 조건부 조합. 정적/동적 캐시 경계 분리.

**산출물**: `packages/prompt_engine/` 패키지 설계 → OpsClaw에 적용

**상세**: [proposals/01-prompt-engine.md](proposals/01-prompt-engine.md)

---

### 2단계: 프롬프트 엔지니어링 적용 (영향도: 대)

**문제**: 프롬프트 내용이 선언적 규칙 위주. 구체적 예시, 도구 사용 가이드, 출력 효율성 지시 부족.

**Claude Code 패턴**: 역할/제약/도구 섹션 분리, "이렇게 하라" 중심, JSON 출력 예시 포함, 안전 행동 구체화.

**산출물**: 개선된 프롬프트 텍스트 → OpsClaw `pi_adapter`, `subagent-runtime`, `portal_routes`에 적용

**상세**: [proposals/02-prompt-engineering.md](proposals/02-prompt-engineering.md)

---

### 3단계: Hook 이벤트 시스템 (영향도: 대)

**문제**: 작업 전후 커스텀 로직 삽입 불가. `notification_service`는 사후 알림만 지원.

**Claude Code 패턴**: 14개 Hook 이벤트, `PreToolUse`에서 approve/block, 비동기 지원, 조건부 실행.

**산출물**: `packages/hook_engine/` 패키지 설계

**상세**: [analysis/hook-system.md](analysis/hook-system.md)

---

### 4단계: Tool 타입 안전성 (영향도: 중)

**문제**: Tool/Skill params가 dict 전달, 런타임 검증 약함, evidence 정규화가 인라인.

**Claude Code 패턴**: Zod 스키마 입출력 검증, `isReadOnly()`/`isDestructive()` 선언, `buildTool()` 팩토리.

**산출물**: `packages/tool_registry/` 강화 설계

**상세**: [analysis/tool-system.md](analysis/tool-system.md)

---

### 5단계: 비용/자원 추적 (영향도: 중)

**문제**: LLM 토큰 사용량/비용 추적 없음, 예산 제한 없음.

**Claude Code 패턴**: 모델별 토큰 추적, USD 환산, `maxBudgetUsd` 예산 강제.

**산출물**: `packages/cost_tracker/` 설계

**상세**: [analysis/cost-tracking.md](analysis/cost-tracking.md)

---

### 6단계: 퍼미션 계층화 (영향도: 중)

**문제**: `rbac_service`/`policy_engine`/`approval_engine` 분산, Tool 레벨 세분화 없음.

**Claude Code 패턴**: 7단계 권한 소스, allow/deny/ask 행동, denial tracking.

**산출물**: `packages/permission_engine/` 통합 설계

**상세**: [analysis/permission-model.md](analysis/permission-model.md)

---

### 7단계: 메모리 고도화 (영향도: 중)

**문제**: 4층 메모리 설계는 있으나 자동화/용량 관리/시맨틱 검색 부족.

**Claude Code 패턴**: MEMORY.md 인덱스, 200줄 용량 제한, 메모리 유형별 분류, "저장하지 않을 것" 명시.

**산출물**: `experience_service` + `retrieval_service` 개선 설계

**상세**: [analysis/memory-system.md](analysis/memory-system.md)
