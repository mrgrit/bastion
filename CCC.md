# CCC — Bastion 운영 지침서

이 파일은 Bastion 에이전트의 장기 기억 및 운영 지침이다.
bastion 시작 시 자동으로 로드되어 시스템 프롬프트에 주입된다.

## 아키텍처

| 컴포넌트 | 경로 | 포트 | 역할 |
|----------|------|------|------|
| ccc-api | apps/ccc_api/ | :9100 | 메인 API (학생/실습/CTF/대전) |
| ccc-ui | apps/ccc-ui/ | - | React 웹 UI (API가 /app/으로 서빙) |
| bastion | apps/bastion/ | - | 운영 관리 에이전트 (이 에이전트) |
| ccc-cli | apps/cli/ | - | 학생용 CLI |

## 서비스 관리

```bash
./dev.sh api       # API 서버 (:9100)
./dev.sh bastion   # Bastion 에이전트
```

## LLM 설정

```
LLM_BASE_URL=http://localhost:11434
LLM_MANAGER_MODEL=gpt-oss:120b    # Manager AI용 (분석/피드백/CTF생성)
LLM_SUBAGENT_MODEL=gemma3:4b      # SubAgent/챗봇용 (경량)
```

## 운영 규칙

- 파괴적 작업(rm -rf /, DROP TABLE 등) 절대 금지
- 학생 데이터 임의 삭제 금지
- 서비스 중지/재시작 시 반드시 사용자 확인
- 배포 전 git status 확인

## 환경별 메모

이 섹션 아래에 환경별 특이사항을 기록한다.
bastion이 학습한 내용은 .ccc/memory/에 저장된다.
