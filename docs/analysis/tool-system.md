# Claude Code Tool 시스템 분석

## 핵심 발견

Claude Code의 도구 시스템은 **Zod 스키마 기반 타입 안전 팩토리 패턴**으로, 60+ 도구를 일관된 인터페이스로 관리한다.

## 코드 구조

### Tool 인터페이스 (`src/Tool.ts`)

```typescript
interface Tool {
  name: string
  description(): string
  inputSchema: ZodSchema           // 입력 검증
  outputSchema?: ZodSchema         // 출력 검증 (선택)
  call(input, context): Promise<ToolResult>
  
  // 안전 분류
  isReadOnly(input): boolean       // 읽기 전용 여부
  isDestructive?(input): boolean   // 파괴적 작업 여부
  isConcurrencySafe(input): boolean // 병렬 실행 안전 여부
  
  // 메타데이터
  isEnabled(): boolean             // 런타임 활성 여부
  interruptBehavior(): 'cancel' | 'block'
  aliases?: string[]               // 하위 호환 이름
}
```

### 팩토리 패턴 (`src/tools.ts`)

```typescript
function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D>
```

모든 도구는 `buildTool()`로 생성 — 기본값 병합 + 타입 추론 자동화.

### 실행 컨텍스트 (`ToolUseContext`)

~300개 필드의 표준화된 실행 환경:
- 앱 상태 접근자 (getAppState, setAppState)
- 중단 시그널 (abortController)
- 권한 체크 (canUseTool)
- 진행 콜백 (onProgress)
- 알림/분석 (addNotification, logEvent)

### 진행 추적 (`ToolCallProgress`)

```typescript
type ToolCallProgress<P> = {
  toolUseId: string
  data: P  // BashProgress | MCPProgress | WebSearchProgress 등
}
```

도구 실행 중 실시간 UI 업데이트 가능.

## OpsClaw 적용 포인트

| Claude Code | OpsClaw 현재 | 개선 방향 |
|------------|-------------|----------|
| Zod 스키마 검증 | JSON Schema 문서만 존재 | `schemas/registry/tools/*.json`을 런타임에 검증 |
| `isDestructive()` | risk_level만 존재 | Tool 정의에 파괴성/읽기전용 플래그 추가 |
| `ToolUseContext` | dict로 params 전달 | 표준화된 ExecutionContext dataclass |
| Progress 콜백 | 없음 | WebSocket 기반 실행 진행 스트리밍 |
| `buildTool()` 팩토리 | YAML seed + DB | 시드 로딩 시 스키마 검증 자동화 |
