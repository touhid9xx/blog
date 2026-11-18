from functools import lru_cache

import boto3
import redis.asyncio as aioredis
from botocore.client import BaseClient, Config

from app.core.config import get_settings

_settings = get_settings()


@lru_cache
def get_redis() -> aioredis.Redis:
    """Async Redis client for DB 2 (cache + pub/sub)."""
    return aioredis.from_url(
        str(_settings.REDIS_URL_CACHE),
        encoding="utf-8",
        decode_responses=True,
    )


@lru_cache
def get_s3() -> BaseClient:
    """boto3 client pointed at MinIO (S3-compatible)."""
    return boto3.client(
        "s3",
        endpoint_url=_settings.MINIO_ENDPOINT,
        aws_access_key_id=_settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=_settings.MINIO_SECRET_KEY,
        region_name=_settings.MINIO_REGION,
        use_ssl=_settings.MINIO_USE_SSL,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
