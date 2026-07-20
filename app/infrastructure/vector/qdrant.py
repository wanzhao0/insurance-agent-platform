"""Qdrant 向量库适配器，可连接本地目录或远程集群。"""

import asyncio
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.domain.models import DocumentResponse, SearchResult


class QdrantVectorStore:
    """在统一集合中按知识库过滤向量，实现跨租户的物理数据隔离补充。"""

    collection_name = "knowledge_documents"

    def __init__(
        self,
        path: str,
        dimension: int,
        url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.dimension = dimension
        if url:
            self.client = QdrantClient(url=url, api_key=api_key)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(self.path))
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """保证集合维度与 Embedding 配置一致。

        维度变更时旧向量不可比较，因此会重建集合；部署变更后必须重新索引全部文档。
        """
        if self.client.collection_exists(self.collection_name):
            info = self.client.get_collection(self.collection_name)
            configured_size = getattr(getattr(info.config, "params", None), "size", None)
            if configured_size == self.dimension:
                return
            self.client.delete_collection(self.collection_name)
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )

    async def reset(self) -> None:
        await asyncio.to_thread(self._reset_sync)

    def _reset_sync(self) -> None:
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self._ensure_collection()

    @staticmethod
    def _point_id(knowledge_base_id: str, document_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"{knowledge_base_id}:{document_id}"))

    async def upsert(
        self, knowledge_base_id: str, document: DocumentResponse, vector: list[float]
    ) -> None:
        """按知识库和分块 ID 覆盖写入，使重复索引保持幂等。"""
        await asyncio.to_thread(
            self.client.upsert,
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=self._point_id(knowledge_base_id, document.document_id),
                    vector=vector,
                    payload={
                        "knowledge_base_id": knowledge_base_id,
                        "document_id": document.metadata.get(
                            "source_document_id", document.document_id
                        ),
                        "chunk_id": document.document_id,
                        "title": document.title,
                        "content": document.content,
                        "metadata": document.metadata,
                    },
                )
            ],
        )

    async def search(
        self, knowledge_base_id: str, vector: list[float], top_k: int
    ) -> list[SearchResult]:
        """只返回指定知识库的近邻结果，过滤条件不可由模型绕过。"""
        query_filter = Filter(
            must=[
                FieldCondition(key="knowledge_base_id", match=MatchValue(value=knowledge_base_id))
            ]
        )
        points = await asyncio.to_thread(self._query, vector, query_filter, top_k)
        results: list[SearchResult] = []
        for point in points:
            payload = point.payload or {}
            results.append(
                SearchResult(
                    document_id=str(payload.get("document_id", "")),
                    title=str(payload.get("title", "")),
                    content=str(payload.get("content", "")),
                    score=round(float(point.score), 4),
                    metadata=payload.get("metadata") or {},
                )
            )
        return results

    def _query(self, vector: list[float], query_filter: Filter, top_k: int):
        if hasattr(self.client, "query_points"):
            return self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            ).points
        return self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

    async def delete(self, knowledge_base_id: str, document_id: str) -> None:
        document_filter = Filter(
            must=[
                FieldCondition(key="knowledge_base_id", match=MatchValue(value=knowledge_base_id)),
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]
        )
        await asyncio.to_thread(
            self.client.delete,
            collection_name=self.collection_name,
            points_selector=FilterSelector(filter=document_filter),
        )

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            await asyncio.to_thread(close)
