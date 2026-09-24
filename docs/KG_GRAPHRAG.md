# 지식 그래프 검색 개선 (GraphRAG 계열 참고)

Bastion 의 지식 그래프(`bastion/graph.py`)를 오픈소스 GraphRAG 계열
(Microsoft GraphRAG, LightRAG, nano-graphrag, LlamaIndex PropertyGraph)의
검증된 기법을 참고해 **경량·무의존·하위호환**으로 개선했다.

## 무엇이 바뀌었나

| 구분 | 이전 | 개선 후 |
|------|------|---------|
| FTS 질의 | 질문 전체를 **정확 구절**(`"..."`)로 매칭 → 다중 단어·한국어 재현율 ≈ 0 | 토큰화 후 **OR 결합**, BM25 랭킹 + 점수 반환 |
| 벡터 검색 | 없음 (embedding 컬럼은 존재하나 미사용) | `vector_search` — 코사인 유사도 (numpy 있으면 가속, 없으면 순수 파이썬) |
| 하이브리드 | 없음 | `hybrid_search` — FTS+벡터를 **RRF(k=60)** 로 융합, 그래프 1-hop 확장 옵션 |
| 임베딩 | 없음 | `embed.py` (사내 Ollama, nomic-embed-text) + `backfill_embeddings` |
| 진입점 | `search_fts` 직접 호출 | `search()` — 임베딩 있으면 hybrid, 없으면 FTS 자동 선택 |

핵심은 **하위호환**이다. 임베딩이 없으면 그래프는 이전과 동일하게 FTS 로만
동작하되, FTS 재현율 버그가 고쳐져 검색 품질이 즉시 향상된다. 임베딩을 채우면
자동으로 하이브리드로 승격된다.

## 참고한 기법과 출처

- **Reciprocal Rank Fusion (RRF, k=60)** — 점수 스케일이 다른 BM25 와 코사인을
  순위만으로 융합. 정규화 불필요, 합의(consensus)를 보상.
  · Azure AI Search hybrid ranking, `blog.serghei.pl/posts/reciprocal-rank-fusion-explained`
- **하이브리드/이중검색 (LightRAG)** — 키워드(엔티티) 경로와 의미(관계/테마) 경로를
  병합. 여기서는 FTS(키워드) + 벡터(의미) 2경로로 축약.
  · `arxiv.org/html/2410.05779v1`
- **그래프 1-hop 확장** — 상위 히트의 이웃을 낮은 가중치로 덧붙여 관계 맥락 보강
  (`hybrid_search(expand=True)`).
- **멱등 인덱싱** — 노드/엣지는 `ON CONFLICT ... DO UPDATE` 로 upsert, 임베딩 백필은
  비어있는 노드만 채워 재개 가능.

## 사용법

```bash
# 1) 임베딩 백필 (사내 Ollama 필요 — 과금 API 아님)
LLM_BASE_URL=http://10.20.30.200:11434 \
  python3 scripts/kg_backfill_embeddings.py            # 전체
  python3 scripts/kg_backfill_embeddings.py --types Playbook Concept

# 2) 코드에서
from bastion.graph import get_graph
g = get_graph()
g.search("C2 비콘 탐지 방법", type="Playbook", limit=5)   # hybrid or FTS 자동
g.hybrid_search("웹 공격 대응", expand=True)              # 이웃 확장 포함
```

환경변수: `LLM_EMBED_MODEL`(기본 `nomic-embed-text:latest`), `BASTION_EMBED=0`(비활성화).

## 다음 후보 (미적용, 규모가 커지면)

- **엔티티 정규화/중복 제거** — `(canon_key, type)` 병합 + 임베딩 블로킹.
- **커뮤니티 요약 (Microsoft GraphRAG)** — Louvain/Leiden 군집 + LLM 요약으로
  "전체 테마" 질문(global) 대응. 현재 운영 KG 규모에선 과함.
- **쿼리 라우팅 (local↔global)** + 토큰 예산 컨텍스트 조립.
