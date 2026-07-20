import asyncio
from pathlib import Path


class LocalObjectStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, tenant_id, knowledge_base_id, document_id, filename, payload) -> str:
        safe_filename = Path(filename).name or "uploaded-file"
        target = self.root / tenant_id / knowledge_base_id / document_id / safe_filename
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, payload)
        return f"local://{target.relative_to(self.root).as_posix()}"

    async def delete(self, uri: str) -> None:
        if not uri.startswith("local://"):
            return
        relative = Path(uri.removeprefix("local://"))
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise ValueError("object URI escapes configured storage root")
        if target.exists():
            await asyncio.to_thread(target.unlink)
