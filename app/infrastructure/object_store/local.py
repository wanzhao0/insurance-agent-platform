"""本地文件系统对象存储适配器，主要用于开发和单机部署。"""

import asyncio
from pathlib import Path


class LocalObjectStore:
    """按租户、知识库和文档隔离上传原文件。"""

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, tenant_id, knowledge_base_id, document_id, filename, payload) -> str:
        """保存字节流并返回稳定的 ``local://`` 对象 URI。"""
        # Path.name 去掉客户端可能携带的目录，避免上传文件名影响目标路径。
        safe_filename = Path(filename).name or "uploaded-file"
        target = self.root / tenant_id / knowledge_base_id / document_id / safe_filename
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, payload)
        return f"local://{target.relative_to(self.root).as_posix()}"

    async def delete(self, uri: str) -> None:
        """删除本地对象，并拒绝任何逃出配置目录的 URI。"""
        if not uri.startswith("local://"):
            return
        relative = Path(uri.removeprefix("local://"))
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise ValueError("object URI escapes configured storage root")
        if target.exists():
            await asyncio.to_thread(target.unlink)
