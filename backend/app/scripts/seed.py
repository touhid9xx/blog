"""
Idempotent seed script: users, chat room, chat messages, blog posts with real media.

Run from `backend/` with the venv active and compose up:

    python -m app.scripts.seed

Media sources: small public-domain sample images and one short sample MP4.
The script uploads media bytes to MinIO (bucket = settings.MINIO_BUCKET_MEDIA)
and stores the resulting public URLs in `posts.media_urls` / `chat_messages.media_url`.

Idempotency:
  - users keyed by email (skip if exists)
  - posts keyed by slug (skip if exists)
  - chat room keyed by name (skip if exists)
  - messages: seeded only if the room was just created (avoids duplicates on re-run)
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import sys
import uuid

import httpx
from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients import get_s3
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.chat import ChatMessage, ChatRoom
from app.models.enums import PostStatus, UserRole
from app.models.post import Post
from app.models.user import User

settings = get_settings()
ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Media helpers
# ---------------------------------------------------------------------------

# Public small sample assets (stable URLs). If any fails to download, we log and skip.
SEED_MEDIA: dict[str, str] = {
    "image_1": "https://images.unsplash.com/photo-1503023345310-bd7c1de61c7d?w=1200&q=80",
    "image_2": "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=1200&q=80",
    "image_3": "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=1200&q=80",
    "video_1": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
}


def _public_url(key: str) -> str:
    """Build a public URL for a MinIO object (no signing — bucket must be public or proxied)."""
    base = settings.MINIO_PUBLIC_ENDPOINT.rstrip("/")
    bucket = settings.MINIO_BUCKET_MEDIA
    return f"{base}/{bucket}/{key}"


async def _download(url: str) -> tuple[bytes, str] | None:
    """Download bytes + guessed content-type. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip()
            if not ctype:
                ctype = mimetypes.guess_type(url)[0] or "application/octet-stream"
            return resp.content, ctype
    except Exception as e:
        print(f"  [WARN] could not download {url}: {type(e).__name__}: {e}")
        return None


def _ext_for(ctype: str) -> str:
    if ctype == "image/jpeg":
        return ".jpg"
    if ctype == "image/png":
        return ".png"
    if ctype == "image/webp":
        return ".webp"
    if ctype == "video/mp4":
        return ".mp4"
    return mimetypes.guess_extension(ctype) or ".bin"


def _upload_and_url(key_prefix: str, filename_hint: str, data: bytes, ctype: str) -> str:
    """
    Upload bytes to MinIO and return the public URL.
    boto3 is sync — callers run this via asyncio.to_thread.
    """
    s3 = get_s3()
    key = f"{key_prefix}/{filename_hint}"
    s3.put_object(  # type: ignore[attr-defined]
        Bucket=settings.MINIO_BUCKET_MEDIA,
        Key=key,
        Body=data,
        ContentType=ctype,
    )
    return _public_url(key)


async def seed_media() -> dict[str, str]:
    """Download each SEED_MEDIA item, upload to MinIO, return {logical_name: public_url}."""
    uploaded: dict[str, str] = {}
    for name, url in SEED_MEDIA.items():
        print(f"  [media] downloading {name} from {url[:60]}...")
        got = await _download(url)
        if got is None:
            continue
        data, ctype = got
        digest = hashlib.sha256(data).hexdigest()[:12]
        ext = _ext_for(ctype)
        filename = f"{name}_{digest}{ext}"
        public_url = await asyncio.to_thread(_upload_and_url, "seed", filename, data, ctype)
        uploaded[name] = public_url
        print(f"  [media] {name}: {ctype} {len(data) // 1024} KB -> {public_url}")
    return uploaded


# ---------------------------------------------------------------------------
# Entity helpers
# ---------------------------------------------------------------------------


async def get_or_create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: UserRole,
) -> User:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        print(f"  [user] exists: {email}")
        return existing
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=ph.hash(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    print(f"  [user] created: {email} ({role.value})")
    return user


async def get_or_create_room(db: AsyncSession, *, name: str) -> tuple[ChatRoom, bool]:
    existing = await db.scalar(select(ChatRoom).where(ChatRoom.name == name))
    if existing is not None:
        print(f"  [room] exists: {name}")
        return existing, False
    room = ChatRoom(id=uuid.uuid4(), name=name, is_private=False)
    db.add(room)
    await db.flush()
    print(f"  [room] created: {name}")
    return room, True


async def get_or_create_post(
    db: AsyncSession,
    *,
    author_id: uuid.UUID,
    title: str,
    slug: str,
    content: str,
    status: PostStatus,
    media_urls: list[str],
) -> Post:
    existing = await db.scalar(select(Post).where(Post.slug == slug))
    if existing is not None:
        print(f"  [post] exists: {slug}")
        return existing
    post = Post(
        id=uuid.uuid4(),
        author_id=author_id,
        title=title,
        slug=slug,
        content=content,
        media_urls=media_urls,
        status=status,
    )
    db.add(post)
    await db.flush()
    print(f"  [post] created: {slug} ({status.value}, {len(media_urls)} media)")
    return post


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    print("== Seeding media to MinIO ==")
    media = await seed_media()
    if not media:
        print("\n[FATAL] No media uploaded — check internet access and MinIO bucket.")
        return 1

    img1 = media.get("image_1")
    img2 = media.get("image_2")
    img3 = media.get("image_3")
    vid1 = media.get("video_1")

    print("\n== Seeding database ==")
    async with SessionLocal() as db:
        # Users
        admin = await get_or_create_user(
            db, email="admin@example.com", password="Admin!2345", role=UserRole.ADMIN
        )
        editor = await get_or_create_user(
            db, email="editor@example.com", password="Editor!2345", role=UserRole.EDITOR
        )
        customer = await get_or_create_user(
            db, email="customer@example.com", password="Customer!2345", role=UserRole.CUSTOMER
        )

        # Chat room + messages
        room, room_created = await get_or_create_room(db, name="general")
        if room_created:
            msgs = [
                ChatMessage(
                    id=uuid.uuid4(),
                    room_id=room.id,
                    sender_id=admin.id,
                    content="Welcome to the general room.",
                ),
                ChatMessage(
                    id=uuid.uuid4(),
                    room_id=room.id,
                    sender_id=editor.id,
                    content="Hi all — excited to try the new platform.",
                ),
                ChatMessage(
                    id=uuid.uuid4(),
                    room_id=room.id,
                    sender_id=customer.id,
                    content="Is anyone else here?",
                ),
                ChatMessage(
                    id=uuid.uuid4(),
                    room_id=room.id,
                    sender_id=editor.id,
                    content="Yes! Poking around the blog catalog now.",
                ),
                ChatMessage(
                    id=uuid.uuid4(),
                    room_id=room.id,
                    sender_id=admin.id,
                    content="Remember: this room is public. No secrets.",
                    media_url=img1,
                ),
                ChatMessage(
                    id=uuid.uuid4(),
                    room_id=room.id,
                    sender_id=customer.id,
                    content="Nice wallpaper 👀",
                    media_url=img2,
                ),
            ]
            db.add_all(msgs)
            print(f"  [chat] inserted {len(msgs)} messages in room '{room.name}'")
        else:
            print("  [chat] room already seeded — skipping messages")

        # Posts (published, published, draft)
        post_1 = await get_or_create_post(
            db,
            author_id=editor.id,
            title="Welcome to the monochrome blog",
            slug="welcome-to-the-monochrome-blog",
            content=(
                "This is the first post on our platform.\n\n"
                "The design is deliberately monochrome — borders, spacing, and "
                "typography do all the work. Media is stored in MinIO and linked "
                "via JSONB in the posts table.\n\n"
                "Below you'll see a hero image and a short sample video."
            ),
            status=PostStatus.PUBLISHED,
            media_urls=[u for u in [img1, vid1] if u],
        )
        post_2 = await get_or_create_post(
            db,
            author_id=editor.id,
            title="A second post: testing images and layout",
            slug="second-post-testing-images-and-layout",
            content=(
                "Multiple images in one post, stored as a JSONB array. "
                "The frontend will render a gallery, and dynamic SEO metadata "
                "will pick the first image as the OpenGraph cover."
            ),
            status=PostStatus.PUBLISHED,
            media_urls=[u for u in [img2, img3] if u],
        )
        post_3 = await get_or_create_post(
            db,
            author_id=editor.id,
            title="Draft: an unfinished idea",
            slug="draft-an-unfinished-idea",
            content="Notes go here. This one should NOT appear in the public catalog.",
            status=PostStatus.DRAFT,
            media_urls=[img3] if img3 else [],
        )

        await db.commit()

        print("\n== Seeded summary ==")
        print(f"  admin     : {admin.email}  (password Admin!2345)")
        print(f"  editor    : {editor.email} (password Editor!2345)")
        print(f"  customer  : {customer.email} (password Customer!2345)")
        print(f"  room      : #{room.name}")
        print(f"  posts     : {post_1.slug}, {post_2.slug}, {post_3.slug}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
