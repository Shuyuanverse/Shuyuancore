from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.persona.profile import StyleDimensions


@dataclass
class AnchorVersion:
    persona_id: str
    version: int = 1
    style_anchor: list[float] = field(default_factory=list)
    decision_anchor: list[float] = field(default_factory=list)
    source_text_hash: str = ""
    created_at: str = ""


_ANCHOR_LAYER: int = 6
_ANCHOR_MEMORY_TYPE: str = "persona_anchor"


class AnchorManager:
    def __init__(
        self,
        embedding_provider: Any | None = None,
        belief_store: Any | None = None,
    ):
        self._embedding_provider = embedding_provider
        self._belief_store = belief_store

    async def create_initial_anchor(
        self, persona_id: str, style_dim: StyleDimensions, core_md: str
    ) -> AnchorVersion:
        style_vec = self._expand_7d_to_128d(style_dim.to_vector())
        decision_vec = await self._embed_and_reduce(core_md, target_dim=256)
        version = AnchorVersion(
            persona_id=persona_id,
            version=1,
            style_anchor=style_vec,
            decision_anchor=decision_vec,
            source_text_hash=str(hash(core_md)),
            created_at="",
        )
        await self._persist_anchor(version)
        return version

    async def create_from_samples(
        self, persona_id: str, content_list: list[str]
    ) -> AnchorVersion:
        import hashlib

        combined = "\n".join(content_list)
        text_hash = hashlib.md5(combined.encode()).hexdigest()

        style_vec = self._expand_7d_to_128d([0.5] * 7)
        decision_vec = await self._embed_and_reduce(combined, target_dim=256)
        version = AnchorVersion(
            persona_id=persona_id,
            version=1,
            style_anchor=style_vec,
            decision_anchor=decision_vec,
            source_text_hash=text_hash,
            created_at="",
        )
        await self._persist_anchor(version)
        return version

    async def load_anchors(
        self, persona_id: str
    ) -> AnchorVersion | None:
        if self._belief_store is None:
            return None

        style_belief = await self._belief_store.get_by_id(
            f"style_anchor_{persona_id}"
        )
        decision_belief = await self._belief_store.get_by_id(
            f"decision_anchor_{persona_id}"
        )

        if style_belief is None and decision_belief is None:
            return None

        style_anchor: list[float] = []
        decision_anchor: list[float] = []

        if style_belief is not None:
            style_anchor = json.loads(style_belief.content)
            style_belief.last_accessed = _ms_time()
            await self._belief_store.update(style_belief)

        if decision_belief is not None:
            decision_anchor = json.loads(decision_belief.content)
            decision_belief.last_accessed = _ms_time()
            await self._belief_store.update(decision_belief)

        return AnchorVersion(
            persona_id=persona_id,
            version=1,
            style_anchor=style_anchor,
            decision_anchor=decision_anchor,
            source_text_hash="",
            created_at="",
        )

    async def _persist_anchor(self, anchor: AnchorVersion) -> None:
        if self._belief_store is None:
            return

        style_content = json.dumps(anchor.style_anchor, ensure_ascii=False)
        decision_content = json.dumps(anchor.decision_anchor, ensure_ascii=False)

        from src.core.interfaces import Belief

        style_belief = await self._belief_store.get_by_id(
            f"style_anchor_{anchor.persona_id}"
        )
        decision_belief = await self._belief_store.get_by_id(
            f"decision_anchor_{anchor.persona_id}"
        )

        now_ms = _ms_time()

        if style_belief is None:
            style_belief = Belief(
                id=f"style_anchor_{anchor.persona_id}",
                content=style_content,
                source="persona_compiler",
                confidence=1.0,
                base_confidence=1.0,
                last_accessed=now_ms,
                memory_type=_ANCHOR_MEMORY_TYPE,
                layer=_ANCHOR_LAYER,
                entities=["anchor", "style", anchor.persona_id],
                timestamp=now_ms,
                metadata={
                    "anchor_type": "style",
                    "version": anchor.version,
                    "persona_id": anchor.persona_id,
                },
            )
            await self._belief_store.add(anchor.persona_id, style_belief)
        else:
            style_belief.content = style_content
            style_belief.last_accessed = now_ms
            style_belief.confidence = 1.0
            await self._belief_store.update(style_belief)

        if decision_belief is None:
            decision_belief = Belief(
                id=f"decision_anchor_{anchor.persona_id}",
                content=decision_content,
                source="persona_compiler",
                confidence=1.0,
                base_confidence=1.0,
                last_accessed=now_ms,
                memory_type=_ANCHOR_MEMORY_TYPE,
                layer=_ANCHOR_LAYER,
                entities=["anchor", "decision", anchor.persona_id],
                timestamp=now_ms,
                metadata={
                    "anchor_type": "decision",
                    "version": anchor.version,
                    "persona_id": anchor.persona_id,
                },
            )
            await self._belief_store.add(anchor.persona_id, decision_belief)
        else:
            decision_belief.content = decision_content
            decision_belief.last_accessed = now_ms
            decision_belief.confidence = 1.0
            await self._belief_store.update(decision_belief)

    def _expand_7d_to_128d(self, vec7: list[float]) -> list[float]:
        import numpy as np

        np.random.seed(42)
        base = np.array(vec7)
        expanded = []
        for v in base:
            expanded.append(float(v))
            expanded.extend((v + np.random.normal(0, 0.05, 18)).tolist())
        expanded = expanded[:128]
        if len(expanded) < 128:
            expanded.extend([0.5] * (128 - len(expanded)))
        return expanded

    async def _embed_and_reduce(self, text: str, target_dim: int) -> list[float]:
        if not text.strip():
            return [0.0] * target_dim

        if self._embedding_provider is not None:
            try:
                if hasattr(self._embedding_provider, "embed"):
                    raw_vec = await self._embedding_provider.embed(text)
                else:
                    raw_vec = await self._embedding_provider(text)
                return self._reduce_dim(raw_vec, target_dim)
            except Exception:
                pass

        try:
            from dashscope import TextEmbedding

            resp = TextEmbedding.call(
                model="text-embedding-v2",
                input=text,
            )
            if resp.status_code == 200:
                raw_vec = resp.output["embeddings"][0]["embedding"]
                return self._reduce_dim(raw_vec, target_dim)
        except Exception:
            pass

        from src.config import get_settings

        get_settings()
        try:
            raw_vec = call_dashscope_embedding(text)
            return self._reduce_dim(raw_vec, target_dim)
        except Exception:
            pass

        return [0.0] * target_dim

    def _reduce_dim(self, vec: list[float], target_dim: int) -> list[float]:
        if len(vec) <= target_dim:
            return vec + [0.0] * (target_dim - len(vec))
        try:
            reduced = _random_projection(vec, target_dim)
            return reduced
        except ImportError:
            return vec[:target_dim]


def _random_projection(vec: list[float], target_dim: int) -> list[float]:
    import numpy as np

    np.random.seed(42)
    projection = np.random.randn(len(vec), target_dim)
    projection /= np.sqrt(target_dim)
    vec_arr = np.array(vec)
    result = vec_arr @ projection
    return result.tolist()


def _ms_time() -> int:
    import time

    return int(time.time() * 1000)


def call_dashscope_embedding(text: str) -> list[float]:
    from dashscope import TextEmbedding

    resp = TextEmbedding.call(
        model="text-embedding-v2",
        input=text,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DashScope embedding failed: {resp.status_code}")
    return resp.output["embeddings"][0]["embedding"]
