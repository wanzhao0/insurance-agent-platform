from app.core.config import Settings
from app.infrastructure.object_store.local import LocalObjectStore
from app.infrastructure.object_store.s3 import S3ObjectStore


def build_object_store(settings: Settings):
    if settings.object_store_provider.lower() == "local":
        return LocalObjectStore(settings.object_store_path)
    if settings.object_store_provider.lower() in {"s3", "minio"}:
        return S3ObjectStore(
            settings.object_store_bucket,
            settings.object_store_region,
            settings.object_store_endpoint_url,
            settings.object_store_access_key.get_secret_value()
            if settings.object_store_access_key
            else None,
            settings.object_store_secret_key.get_secret_value()
            if settings.object_store_secret_key
            else None,
        )
    raise ValueError(f"unsupported object store provider: {settings.object_store_provider}")
