"""Text to numbers. Two texts with the same meaning get close numbers."""
from functools import lru_cache
import numpy as np


@lru_cache(maxsize=1)
def _model():
    from wordllama import WordLlama
    return WordLlama.load(disable_download=True)  # small model, ships inside the pip package


def embed(texts: list[str]) -> np.ndarray:
    v = _model().embed(texts)
    return (v / np.linalg.norm(v, axis=1, keepdims=True)).astype(np.float32)


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]
