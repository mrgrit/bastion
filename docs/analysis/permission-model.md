# Claude Code 퍼미션 모델 분석

## 핵심 발견

Claude Code는 **7단계 권한 소스**에서 규칙을 수집하고, `allow/deny/ask` 3가지 행동으로 결정하며, denial tracking으로 자동 에스컬레이션한다.

## 코드 구조

### 퍼미션 모드 (`src/types/permissions.ts`)

```typescript
const PERMISSION_MODES = ['acceptEdits', 'bypassPermissions', 'default', 'dontAsk', 'plan']
```

### 권한 소스 우선순위

```
1. userSettings     → ~/.claude/settings.json
2. projectSettings  → .claude/settings.json
3. localSettings    → 로컬 환경
4. flagSettings     → 정책 서버
5. policySettings   → 관리 정책
6. cliArg          → --always-allow/--always-deny
7. session         → 세션 중 변경
```

### 규칙 구조

```typescript
type PermissionRule = {
  source: PermissionRuleSource
  ruleBehavior: 'allow' | 'deny' | 'ask'
  ruleValue: {
    toolName: string
    ruleContent?: string  // 세분화 매처
  }
}
```

### Denial Tracking

연속 거부 횟수를 추적하여 임계값 초과 시 사용자에게 강제 재확인.

## OpsClaw 적용 포인트

| Claude Code | OpsClaw 현재 | 개선 방향 |
|------------|-------------|----------|
| 7단계 소스 | rbac_service만 | API Key + RBAC + Policy + Hook 통합 |
| allow/deny/ask | 허용/거부만 | ask → 사용자 확인 대기 기능 추가 |
| Tool 레벨 규칙 | 문자열 권한만 | `tool_name:params` 패턴 매칭 |
| Denial tracking | 없음 | 연속 실패/거부 자동 에스컬레이션 |
| 퍼미션 모드 | 없음 | 운영모드(normal/emergency/readonly) 도입 |
