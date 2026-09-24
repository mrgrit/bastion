"""Bastion 임베딩 클라이언트 — 로컬/사내 Ollama (nomic-embed-text 등).

지식 그래프의 벡터 검색(hybrid)을 위한 노드 임베딩을 생성한다.
과금 API를 쓰지 않으며(사내 Ollama), 서버가 없으면 조용히 비활성화되어
그래프는 FTS 전용으로 계속 동작한다.

환경변수:
  LLM_BASE_URL       — Ollama 베이스 URL (예: http://10.20.30.200:11434)
  LLM_EMBED_MODEL    — 임베딩 모델 (기본: nomic-embed-text:latest)
  BASTION_EMBED      — "0" 이면 전역 비활성화
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

DEFAULT_MODEL = "nomic-embed-text:latest"


class Embedder:
    def __init__(self, base_url: str = "", model: str = "", timeout: float = 60.0):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.getenv("LLM_EMBED_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        self.enabled = bool(self.base_url) and os.getenv("BASTION_EMBED", "1") != "0"
        self._dim: Optional[int] = None

    def embed(self, text: str) -> Optional[list[float]]:
        text = (text or "").strip()
        if not self.enabled or not text:
            return None
        try:
            r = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text[:8000]},
                timeout=self.timeout,
            )
            r.raise_for_status()
            emb = r.json().get("embedding")
            if emb:
                self._dim = len(emb)
                return emb
        except Exception:
            return None
        return None

    def available(self) -> bool:
        return self.enabled and self.embed("ping") is not None


_default: Optional[Embedder] = None


def get_embedder() -> Embedder:
    global _default
    if _default is None:
        _default = Embedder()
    return _default
