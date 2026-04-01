# Claude Code 시스템 프롬프트 아키텍처 분석

## 핵심 발견

Claude Code의 시스템 프롬프트(`src/constants/prompts.ts`, 914줄)는 단일 문자열이 아니라 **14개 독립 섹션의 조건부 조합**으로 구성된다. 각 섹션은 함수로 분리되어 있고, 런타임 환경(활성 도구, 모델, 설정, MCP 서버)에 따라 동적으로 포함/제외된다.

## 코드 구조

### 진입점: `getSystemPrompt()` (라인 444-577)

```typescript
export async function getSystemPrompt(
  tools: Tools,
  model: string,
  additionalWorkingDirectories?: string[],
  mcpClients?: MCPServerConnection[],
): Promise<string[]>
```

반환값이 `string`이 아닌 **`string[]`** — 섹션 배열을 반환하여 API 레벨에서 캐싱 최적화 가능.

### 정적 섹션 (캐시 가능, 경계 이전)

| 함수 | 라인 | 역할 |
|------|------|------|
| `getSimpleIntroSection()` | 175-183 | 역할 정의 + 사이버 리스크 지시 |
| `getSimpleSystemSection()` | 186-197 | 도구 실행, 권한, 시스템 태그, Hook, 자동 압축 |
| `getSimpleDoingTasksSection()` | 199-253 | 코딩 규범, 보안, 코드 스타일 15개 규칙 |
| `getActionsSection()` | 255-267 | 위험 행동 판단 기준, 확인 필요 예시 |
| `getUsingYourToolsSection()` | 269-314 | 도구별 사용 가이드 (Bash 대신 전용 도구) |
| `getSimpleToneAndStyleSection()` | 430-442 | 이모지 금지, 간결성, file:line 참조 |
| `getOutputEfficiencySection()` | 403-428 | 출력 효율성 (결론 먼저, 1문장 원칙) |

### 경계 마커 (라인 114-115)

```typescript
export const SYSTEM_PROMPT_DYNAMIC_BOUNDARY = '__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__'
```

이 마커 이전: 모든 사용자/세션에 공통 → **글로벌 캐시** 가능
이 마커 이후: 세션별 달라짐 → **캐시 불가**

### 동적 섹션 (세션별, 경계 이후)

| 섹션 ID | 함수 | 내용 |
|---------|------|------|
| `session_guidance` | `getSessionSpecificGuidanceSection()` | 활성 도구에 따른 안내 |
| `memory` | `loadMemoryPrompt()` | MEMORY.md 로드 |
| `env_info_simple` | `computeSimpleEnvInfo()` | CWD, git, OS, 모델명 |
| `language` | `getLanguageSection()` | 사용자 언어 설정 |
| `output_style` | `getOutputStyleSection()` | 커스텀 출력 스타일 |
| `mcp_instructions` | `getMcpInstructionsSection()` | MCP 서버별 사용 안내 |
| `scratchpad` | `getScratchpadInstructions()` | 작업 디렉토리 안내 |
| `frc` | `getFunctionResultClearingSection()` | 도구 결과 압축 안내 |

### 섹션 등록 시스템 (systemPromptSections.ts)

```typescript
// 캐시 안전 — 내용이 변해도 캐시 키에 영향 없음
systemPromptSection('memory', () => loadMemoryPrompt())

// 캐시 위험 — MCP 서버 연결 상태가 바뀌면 캐시 무효화 필요
DANGEROUS_uncachedSystemPromptSection('mcp_instructions', () => ..., 'MCP servers connect/disconnect')
```

## OpsClaw 현재 상태 vs Claude Code

| 측면 | OpsClaw | Claude Code |
|------|---------|-------------|
| 프롬프트 크기 | 3줄 고정 (120B) | 14섹션 ~5,000토큰 |
| 동적 구성 | 없음 (`context.get("system_prompt")` 오버라이드만) | 환경/도구/설정별 조건부 조합 |
| 캐시 전략 | 없음 | 정적/동적 경계 분리 |
| 도구 가이드 | 없음 | 도구별 사용 시점/방법 명시 |
| 안전 규칙 | 문서에만 존재 (`agent-system-prompt.md`) | 런타임 프롬프트에 직접 삽입 |
| 메모리 연동 | 없음 | `loadMemoryPrompt()` 자동 로드 |
| A/B 테스트 | 없음 | `feature()` 플래그로 섹션별 실험 |

## 적용 가능 패턴

### 패턴 1: 섹션 함수 분리
각 프롬프트 섹션을 독립 함수로 만들어 테스트/수정/교체 가능하게 한다.

### 패턴 2: 정적/동적 경계
역할 정의, 안전 규칙 등 불변 내용은 캐시하고, RAG 결과/로컬 지식 등 가변 내용만 매번 재구성.

### 패턴 3: 도구 인식 프롬프트
활성화된 Tool/Skill 목록을 프롬프트에 동적 삽입하여 LLM이 적절한 도구를 선택하도록 유도.

### 패턴 4: 환경 컨텍스트 주입
CWD, 대상 서버, 인프라 매핑 등을 프롬프트에 포함하여 LLM이 환경을 인식.

### 패턴 5: Feature Flag
새 프롬프트 섹션을 점진적으로 활성화하여 품질 영향을 측정.
