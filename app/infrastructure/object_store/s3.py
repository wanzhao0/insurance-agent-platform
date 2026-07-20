import asyncio
from pathlib import Path


class S3ObjectStore:
    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
    ) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    async def put(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        document_id: str,
        filename: str,
        payload: bytes,
    ) -> str:
        key = "/".join(
            (
                self._segment(tenant_id),
                self._segment(knowledge_base_id),
                self._segment(document_id),
                Path(filename).name or "uploaded-file",
            )
        )
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=payload)
        return f"s3://{self.bucket}/{key}"

    async def delete(self, uri: str) -> None:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix):
            return
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=self.bucket,
            Key=uri.removeprefix(prefix),
        )

    @staticmethod
    def _segment(value: str) -> str:
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("invalid object store path segment")
        return value
