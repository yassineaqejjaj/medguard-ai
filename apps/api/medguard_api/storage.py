"""Evidence storage. Objects are written to an S3-compatible store (SeaweedFS) and addressed by tenant-scoped keys;
their SHA-256 is recorded in the database and re-checked on every read, so silent tampering is detectable."""
import asyncio
import hashlib
import uuid
from typing import Protocol

from .config import get_settings


class IntegrityError(Exception):
    pass


class Store(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class MemoryStore:
    objects: dict[str, bytes] = {}

    async def put(self, key, data, content_type):
        self.objects[key] = data

    async def get(self, key):
        return self.objects[key]

    async def delete(self, key):
        self.objects.pop(key, None)


class S3Store:
    def __init__(self):
        import boto3
        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client("s3", endpoint_url=s.s3_endpoint, aws_access_key_id=s.s3_access_key,
                                   aws_secret_access_key=s.s3_secret_key, region_name="us-east-1")
        self._ready = False

    def _ensure(self):
        if not self._ready:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except Exception:
                self.client.create_bucket(Bucket=self.bucket)
            self._ready = True

    async def put(self, key, data, content_type):
        def go():
            self._ensure()
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        await asyncio.to_thread(go)

    async def get(self, key):
        return await asyncio.to_thread(lambda: self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read())

    async def delete(self, key):
        await asyncio.to_thread(lambda: self.client.delete_object(Bucket=self.bucket, Key=key))


_store: Store | None = None
_memory = MemoryStore()


def get_store() -> Store:
    global _store
    if get_settings().evidence_backend == "memory":
        return _memory
    if _store is None:
        _store = S3Store()
    return _store


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_key(org_id: uuid.UUID, run_id: uuid.UUID | None, kind: str, name: str) -> str:
    return f"{org_id}/{run_id or 'org'}/{kind}/{name}"


async def read_verified(key: str, expected_sha256: str) -> bytes:
    data = await get_store().get(key)
    if sha256(data) != expected_sha256:
        raise IntegrityError(f"stored object {key} no longer matches its recorded hash")
    return data
