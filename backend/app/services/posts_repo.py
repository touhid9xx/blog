import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PostStatus
from app.models.post import Post


async def get_by_id(session: AsyncSession, post_id: uuid.UUID) -> Post | None:
    return await session.get(Post, post_id)


async def get_by_slug(session: AsyncSession, slug: str) -> Post | None:
    result = await session.execute(select(Post).where(Post.slug == slug))
    return result.scalar_one_or_none()


async def slug_exists(session: AsyncSession, slug: str) -> bool:
    result = await session.execute(select(func.count()).select_from(Post).where(Post.slug == slug))
    return (result.scalar_one() or 0) > 0


async def list_posts(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    status: PostStatus | None = None,
    author_id: uuid.UUID | None = None,
) -> tuple[list[Post], int]:
    stmt = select(Post)
    count_stmt = select(func.count()).select_from(Post)
    if status is not None:
        stmt = stmt.where(Post.status == status)
        count_stmt = count_stmt.where(Post.status == status)
    if author_id is not None:
        stmt = stmt.where(Post.author_id == author_id)
        count_stmt = count_stmt.where(Post.author_id == author_id)

    stmt = stmt.order_by(Post.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return list(rows), int(total)


async def create_post(
    session: AsyncSession,
    *,
    author_id: uuid.UUID,
    title: str,
    slug: str,
    content: str,
    media_urls: list[str],
    status: PostStatus,
) -> Post:
    post = Post(
        author_id=author_id,
        title=title,
        slug=slug,
        content=content,
        media_urls=media_urls,
        status=status,
    )
    session.add(post)
    await session.flush()
    return post
