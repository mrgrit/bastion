# Claude Code 비용 추적 분석

## 핵심 발견

Claude Code는 모델별 input/output/cache 토큰을 실시간 추적하고, USD 환산하며, 세션/태스크 예산을 강제한다.

## 코드 구조

### 토큰 추적 (`src/cost-tracker.ts`)

```typescript
type ModelUsage = {
  [modelName: string]: {
    inputTokens: number
    outputTokens: number
    cacheCreationInputTokens?: number
    cacheReadInputTokens?: number
  }
}
```

### 비용 계산 (`src/utils/modelCost.ts`)

모델별 가격 테이블:
- input token rate
- output token rate
- cache write rate (보통 input의 25%)
- cache read rate (보통 input의 10%)

### 예산 강제

```typescript
// QueryEngineConfig
maxBudgetUsd?: number      // 세션 전체 한도
taskBudget?: { total: number }  // 태스크별 한도
```

API 호출 전 잔여 예산 체크 → 초과 시 실행 중단.

### 메트릭 함수

- `getTotalCostUSD()` → 누적 비용
- `getTotalInputTokens()` → 입력 토큰
- `getTotalOutputTokens()` → 출력 토큰
- `getTotalAPIDuration()` → API 레이턴시
- `getTotalToolDuration()` → 도구 실행 시간

## OpsClaw 적용 포인트

| Claude Code | OpsClaw 현재 | 개선 방향 |
|------------|-------------|----------|
| 토큰 추적 | 없음 | Ollama 응답에서 usage 추출 |
| USD 환산 | 없음 | GPU 시간 기반 비용 산정 |
| 예산 강제 | 없음 | 프로젝트별 max_tokens 제한 |
| 레이턴시 추적 | duration_s만 | API+실행 분리 추적 |
| 대시보드 | 없음 | Web UI 비용 위젯 |
