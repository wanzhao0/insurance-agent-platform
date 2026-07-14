import hashlib
import math
import re


class HashEmbeddingClient:
    """Deterministic local embeddings for development and offline deployments.

    This is useful as a zero-credential fallback, while the provider interface
    keeps production deployments free to use a hosted embedding model.
    """

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 8) for value in vector]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        stopwords = (
            "请告诉我",
            "有什么",
            "请问",
            "保险产品",
            "保险",
            "产品",
            "可以",
            "推荐",
            "需要",
            "什么",
            "告诉我",
            "我",
            "你",
            "吗",
            "呢",
            "的",
            "请",
        )
        tokens: list[str] = []
        for segment in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
            if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
                for stopword in stopwords:
                    segment = segment.replace(stopword, "")
                if not segment:
                    continue
                if len(segment) == 1:
                    tokens.append(segment)
                else:
                    tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
            elif len(segment) > 1:
                tokens.append(segment)
        return list(dict.fromkeys(tokens))
