#!/usr/bin/env python3
"""지식 그래프 노드 임베딩 백필 — hybrid 검색 활성화용.

사내 Ollama(LLM_BASE_URL, LLM_EMBED_MODEL=nomic-embed-text)로 임베딩을 생성해
nodes.embedding 을 채운다. 재개 가능(이미 채워진 노드는 건너뜀). 과금 API 미사용.

사용:
  LLM_BASE_URL=http://10.20.30.200:11434 python3 scripts/kg_backfill_embeddings.py
옵션:
  --types Playbook Concept ...   특정 타입만
  --limit N                      최대 N개
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bastion.graph import get_graph  # noqa: E402
from bastion.embed import get_embedder  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--db", default="")
    a = ap.parse_args()
    g = get_graph(a.db)
    emb = get_embedder()
    if not emb.enabled:
        print("LLM_BASE_URL 이 설정되지 않았습니다. (임베딩 서버 필요)")
        sys.exit(1)
    print(f"임베딩 백필 시작 — 모델 {emb.model} @ {emb.base_url}")
    res = g.backfill_embeddings(embedder=emb, types=a.types, limit=a.limit)
    print(res)
    print("커버리지:", "예" if g.has_embeddings() else "아니오")


if __name__ == "__main__":
    main()
