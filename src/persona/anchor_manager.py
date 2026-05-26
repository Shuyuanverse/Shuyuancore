from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from src.persona.profile import StyleDimensions


@dataclass
class AnchorVersion:
    persona_id: str
    version: int = 1
    style_anchor: list[float] = field(default_factory=list)
    decision_anchor: list[float] = field(default_factory=list)
    source_text_hash: str = ""
    created_at: str = ""


class AnchorManager:
    def __init__(self, embedding_provider: Optional[object] = None):
        self._embedding_provider = embedding_provider

    async def create_initial_anchor(
        self, persona_id: str, style_dim: StyleDimensions, core_md: str
    ) -> AnchorVersion:
        style_vec = self._expand_7d_to_128d(style_dim.to_vector())
        decision_vec = await self._embed_and_reduce(core_md, target_dim=256)
        return AnchorVersion(
            persona_id=persona_id,
            version=1,
            style_anchor=style_vec,
            decision_anchor=decision_vec,
            source_text_hash=str(hash(core_md)),
            created_at="",
        )

    async def create_from_samples(
        self, persona_id: str, content_list: list[str]
    ) -> AnchorVersion:
        import hashlib
        combined = "\n".join(content_list)
        text_hash = hashlib.md5(combined.encode()).hexdigest()

        style_vec = self._expand_7d_to_128d([0.5] * 7)
        decision_vec = await self._embed_and_reduce(combined, target_dim=256)
        return AnchorVersion(
            persona_id=persona_id,
            version=1,
            style_anchor=style_vec,
            decision_anchor=decision_vec,
            source_text_hash=text_hash,
            created_at="",
        )

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
            import numpy as np
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
        settings = get_settings()
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
            import numpy as np
            from sklearn.decomposition import PCA
            pca = PCA(n_components=target_dim)
            reduced = pca.fit_transform(np.array([vec]))
            return reduced[0].tolist()
        except ImportError:
            return vec[:target_dim]


def call_dashscope_embedding(text: str) -> list[float]:
    import numpy as np
    from dashscope import TextEmbedding
    resp = TextEmbedding.call(
        model="text-embedding-v2",
        input=text,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DashScope embedding failed: {resp.status_code}")
    return resp.output["embeddings"][0]["embedding"]