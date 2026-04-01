# Bastion — OpsClaw Prompt & Agent Intelligence Layer

Bastion은 [OpsClaw](https://github.com/mrgrit/opsclaw) IT 운영/보안 자동화 플랫폼의 **프롬프트 엔지니어링 및 에이전트 지능 계층**이다.

[Claude Code](https://claude.ai/code) 소스코드(`src/`)의 아키텍처를 분석하여, OpsClaw의 LLM 호출 품질, 안전성, 확장성을 체계적으로 개선하는 것이 목표다.

## 배경

OpsClaw는 M0~M26 마일스톤을 완료하며 Manager API, SubAgent Runtime, Playbook Engine, PoW 블록체인, RL 보상 등 핵심 기능을 구축했다. 그러나 LLM과의 상호작용 품질 — 시스템 프롬프트, 도구 사용 가이드, 퍼미션 모델, 비용 추적 — 은 아직 초기 수준이다.

Claude Code(`src/`)는 60+ 도구, 50+ 명령, 14개 프롬프트 섹션, 다층 퍼미션, Hook 시스템, 비용 추적 등 생산 수준의 에이전트 인프라를 갖추고 있다. 이 검증된 패턴을 OpsClaw에 맞게 재설계하여 적용한다.

## 분석 대상 (src/)

`src/`는 Claude Code의 TypeScript 소스코드 스냅샷이다. 직접 실행 대상이 아닌 **아키텍처 레퍼런스**로 사용한다.

| 영역 | 핵심 파일 | OpsClaw 적용 대상 |
|------|----------|------------------|
| 프롬프트 구조 | `src/constants/prompts.ts` (914줄) | prompt_engine 패키지 |
| 도구 시스템 | `src/Tool.ts`, `src/tools.ts` | tool_registry 강화 |
| 퍼미션 | `src/types/permissions.ts`, `src/hooks/toolPermission/` | permission_engine |
| Hook 시스템 | `src/types/hooks.ts`, `src/utils/hooks/` | hook_engine |
| 비용 추적 | `src/cost-tracker.ts`, `src/utils/modelCost.ts` | cost_tracker |
| 메모리 | `src/memdir/` | experience_service 고도화 |
| 스킬 | `src/skills/`, `src/tools/SkillTool/` | playbook_engine 개선 |
| 상태 관리 | `src/state/store.ts` | 프로젝트 상태 반응형 |

## 개선 로드맵

| 단계 | 영역 | 난이도 | 영향도 | 상태 |
|------|------|--------|--------|------|
| 1 | 시스템 프롬프트 아키텍처 | 중 | 극대 | 진행 중 |
| 2 | 프롬프트 엔지니어링 적용 | 낮 | 대 | 대기 |
| 3 | Hook 이벤트 시스템 | 중 | 대 | 대기 |
| 4 | Tool 타입 안전성 | 중 | 중 | 대기 |
| 5 | 비용/자원 추적 | 낮 | 중 | 대기 |
| 6 | 퍼미션 계층화 | 높 | 중 | 대기 |
| 7 | 메모리 고도화 | 중 | 중 | 대기 |

상세 계획: [docs/plan.md](docs/plan.md)

## 디렉토리 구조

```
bastion/
├── src/                        # Claude Code 소스 (분석 레퍼런스)
├── docs/
│   ├── plan.md                 # 전체 개선 계획
│   ├── analysis/               # Claude Code 아키텍처 분석
│   │   ├── prompt-architecture.md
│   │   ├── tool-system.md
│   │   ├── permission-model.md
│   │   ├── hook-system.md
│   │   ├── cost-tracking.md
│   │   └── memory-system.md
│   └── proposals/              # OpsClaw 적용 제안서
│       ├── 01-prompt-engine.md
│       └── 02-prompt-engineering.md
├── CLAUDE.md                   # AI 에이전트 작업 가이드
└── README.md
```

## 관련 프로젝트

- **OpsClaw**: https://github.com/mrgrit/opsclaw — IT 운영/보안 자동화 control-plane
- **Claude Code**: `src/` 디렉토리 — Anthropic의 CLI 에이전트 (분석 레퍼런스)
