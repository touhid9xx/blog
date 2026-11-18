# blog/backend/app/api/health.py
import asyncio
from typing import Any, Literal, cast

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.clients import get_redis, get_s3
from app.db.session import engine

router = APIRouter(tags=["ops"])


class HealthPart(BaseModel):
    status: Literal["ok", "fail"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "fail"]
    database: HealthPart
    redis: HealthPart
    object_storage: HealthPart


async def _check_db() -> HealthPart:
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return HealthPart(status="ok")
    except Exception as e:
        return HealthPart(status="fail", detail=f"{type(e).__name__}: {e}")


async def _check_redis() -> HealthPart:
    try:
        redis_client = cast(Any, get_redis())
        pong = await redis_client.ping()
        if pong is True:
            return HealthPart(status="ok")
        return HealthPart(status="fail", detail=f"unexpected ping result: {pong!r}")
    except Exception as e:
        return HealthPart(status="fail", detail=f"{type(e).__name__}: {e}")


def _check_minio_sync() -> HealthPart:
    """boto3 is sync; we'll run it in a thread from the async caller."""
    try:
        s3 = cast(Any, get_s3())
        s3.head_bucket(Bucket=_bucket())
        return HealthPart(status="ok")
    except Exception as e:
        return HealthPart(status="fail", detail=f"{type(e).__name__}: {e}")


def _bucket() -> str:
    from app.core.config import get_settings

    return get_settings().MINIO_BUCKET_MEDIA


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    db_part, redis_part, minio_part = await asyncio.gather(
        _check_db(),
        _check_redis(),
        asyncio.to_thread(_check_minio_sync),
    )
    all_ok = all(p.status == "ok" for p in (db_part, redis_part, minio_part))
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if all_ok else "fail",
        database=db_part,
        redis=redis_part,
        object_storage=minio_part,
    )
