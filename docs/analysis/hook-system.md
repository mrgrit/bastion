# Claude Code Hook 시스템 분석

## 핵심 발견

Claude Code는 **14개 라이프사이클 이벤트**에 외부 Hook을 등록할 수 있으며, PreToolUse Hook은 실행을 차단(block)할 수 있다.

## 코드 구조

### Hook 이벤트 (`src/types/hooks.ts`)

```typescript
const HOOK_EVENTS = [
  'SessionStart', 'SessionEnd',
  'UserPromptSubmit', 'UserPromptStart',
  'Setup',
  'PreToolUse', 'PostToolUse',
  'PreCompact', 'PostCompact',
  'SubagentStart', 'SubagentEnd',
  'FileChanged',
  'UserInterrupt',
]
```

### Hook 유형

- **HTTP Hook**: 외부 URL로 POST → JSON 응답
- **Agent Hook**: 에이전트 프로세스 생성
- **Prompt Hook**: 프롬프트 주입

### Hook 응답

```typescript
type HookResponse = {
  continue?: boolean          // false → 실행 중단
  decision?: 'approve' | 'block'  // PreToolUse 전용
  reason?: string
  systemMessage?: string      // 경고 메시지
  modified_input?: object     // 입력 수정
}
```

### 비동기 Hook

```typescript
type AsyncHookConfig = {
  asyncTimeout?: number       // 기본 15초
  attachResponseAs?: 'content_block' | 'message'
  trackable?: boolean
}
```

## OpsClaw 적용 포인트

| Claude Code | OpsClaw 현재 | 개선 방향 |
|------------|-------------|----------|
| 14개 이벤트 | notification만 | 10개 운영 이벤트 정의 |
| PreToolUse block | 없음 | pre_dispatch에서 실행 차단 가능 |
| 조건부 실행 | 없음 | Python expression 조건 |
| 비동기 + 타임아웃 | 없음 | 15초 기본 타임아웃 |
| Hook 등록 | notification_rules | DB + API로 Hook CRUD |
