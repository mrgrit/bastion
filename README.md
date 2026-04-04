# Bastion

> 실무 운영/보안 AI 에이전트 시스템

Bastion은 IT 인프라의 자산 관리, SubAgent 자동 설치, AI 기반 시스템 운영/보안 자동화를 수행하는 실무용 에이전트 시스템이다. 자연어로 작업을 요청하면 LLM이 실행 계획을 생성하고 SubAgent로 실행한다.

## 주요 기능

- **자산 관리**: 서버 등록 → SubAgent 자동 설치 → 헬스체크 → 온보딩
- **AI 에이전트**: 자연어 → LLM 실행 계획 → SubAgent 명령 실행 → PoW 블록체인 기록
- **대시보드**: 자산 현황, 운영 이력, 블록체인, 설정
- **CLI**: `bastion assets|add|onboard|health|task|analyze|dashboard|blocks`

## 아키텍처

```
사용자 (웹 UI / CLI)
    |
    v
bastion-api (:9000)
    |-- 자산 CRUD + 부트스트랩
    |-- AI 에이전트 (agent_orchestrator)
    |-- 블록체인 (PoW)
    |-- 대시보드
    |
    v
SubAgent (:8002)  -- 각 서버에 설치
    |-- 명령 실행
    |-- 헬스체크
```

## AI 작업 플로우

```
"secu 서버 패치 적용해줘"
  -> LLM(Ollama) -> 실행 계획 생성
  -> SubAgent(secu:8002) -> 명령 실행
  -> 결과 -> PoW 블록 자동 생성
  -> 작업 이력 DB 기록
```

## Quick Start

```bash
# DB
docker compose -f docker/docker-compose.yaml up -d

# API
cp .env.example .env
./dev.sh api    # http://localhost:9000

# CLI
export PYTHONPATH=$(pwd)
python -m apps.cli.main assets
python -m apps.cli.main task "서버 상태 확인"
```

## API

| Method | Path | 기능 |
|--------|------|------|
| POST | `/assets` | 자산 등록 |
| POST | `/assets/{id}/bootstrap` | SubAgent 설치 |
| POST | `/assets/{id}/onboard` | 전체 온보딩 |
| GET | `/assets/{id}/health` | 헬스체크 |
| POST | `/agent/task` | AI 작업 실행 |
| POST | `/agent/analyze` | 실행 없이 분석만 |
| GET | `/dashboard/summary` | 대시보드 |
| GET | `/blockchain/blocks` | 블록 목록 |
| GET | `/blockchain/verify` | 체인 검증 |

## 관련 시스템

| 시스템 | 역할 |
|--------|------|
| [OpsClaw](https://github.com/mrgrit/opsclaw) | 연구/개발 + 중앙서버 |
| [CCC](https://github.com/mrgrit/ccc) | 사이버보안 교육 플랫폼 |

## 참고: Claude Code 분석

`src/` 디렉토리는 Claude Code 소스코드 읽기 전용 레퍼런스이다. `docs/analysis/`에 분석 결과, `docs/proposals/`에 OpsClaw 적용 제안서가 있다. 이 분석을 기반으로 6개 패키지(prompt_engine, hook_engine, tool_validator, cost_tracker, permission_engine, memory_manager)를 OpsClaw에 구현하였다.

## 기술 스택

Python 3.11 / FastAPI / PostgreSQL / React / Ollama LLM

## License

MIT
