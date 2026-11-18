"""Manual smoke test: ping Postgres, Redis, MinIO. Exit 0 on success."""

from __future__ import annotations

import asyncio
import sys

from app.api.health import _check_db, _check_minio_sync, _check_redis


async def main() -> int:
    db, redis_part = await asyncio.gather(_check_db(), _check_redis())
    minio = await asyncio.to_thread(_check_minio_sync)

    results = {"database": db, "redis": redis_part, "object_storage": minio}
    failures = 0
    for name, part in results.items():
        if part.status == "ok":
            print(f"  [OK]   {name}")
        else:
            failures += 1
            print(f"  [FAIL] {name}: {part.detail}")

    if failures:
        print(f"\n{failures} dependency check(s) failed.")
        return 1
    print("\nAll dependencies reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
