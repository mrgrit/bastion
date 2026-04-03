# Bastion — 실무 운영/보안 AI 에이전트 시스템

자산 등록 → SubAgent 자동 설치 → AI 기반 시스템 운영/보안 자동화.

## 아키텍처

| 컴포넌트 | 경로 | 포트 | 역할 |
|----------|------|------|------|
| bastion-api | apps/bastion-api/ | :9000 | 메인 API (자산/운영/블록체인) |
| bastion-ui | apps/bastion-ui/ | - | React 관리 대시보드 |
| bastion-cli | apps/cli/ | - | CLI 도구 |

## 패키지

| 패키지 | 역할 | 마일스톤 |
|--------|------|---------|
| agent_orchestrator | AI 오케스트레이션 (pi_adapter+prompt_engine) | M5 |
| infra_scanner | 자산 자동 탐색 | M3 |

## 개발

```bash
# PostgreSQL
docker compose -f docker/docker-compose.yaml up -d

# API 서버
cp .env.example .env
./dev.sh api

# CLI
export PYTHONPATH=$(pwd)
python -m apps.cli.main assets
```

## API 인증

모든 API 호출에 `X-API-Key` 헤더 필요.
기본 키: `bastion-api-key-2026`

## 레퍼런스 분석 (src/)

`src/`는 Claude Code 소스 읽기 전용 레퍼런스.
분석 결과: `docs/analysis/`, 제안: `docs/proposals/`

## 관련 시스템

- **opsclaw** (연구용): https://github.com/mrgrit/opsclaw
- **CCC** (교육용): https://github.com/mrgrit/ccc
- **중앙서버**: opsclaw 레포 내 `apps/central-server/` (:7000)
