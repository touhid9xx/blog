import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PostStatus, UserRole
from app.models.post import Post
from app.models.user import User
from app.services import posts_repo
from app.services.slug import slugify, with_suffix


class PostError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _is_moderator(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.EDITOR)


def _can_view(user: User | None, post: Post) -> bool:
    if post.status == PostStatus.PUBLISHED:
        return True
    if user is None:
        return False
    if _is_moderator(user):
        return True
    return post.author_id == user.id


def _can_edit(user: User, post: Post) -> bool:
    if _is_moderator(user):
        return True
    # customer: only their own, and only drafts
    return post.author_id == user.id and post.status == PostStatus.DRAFT


def _can_delete(user: User, post: Post) -> bool:
    if _is_moderator(user):
        return True
    # customer: their own drafts only
    return post.author_id == user.id and post.status == PostStatus.DRAFT


def _can_use_status(user: User, target: PostStatus) -> bool:
    if target == PostStatus.DRAFT:
        return True  # everyone can save as draft
    return _is_moderator(user)


async def _unique_slug(session: AsyncSession, title: str) -> str:
    base = slugify(title)
    candidate = base
    for _ in range(5):
        if not await posts_repo.slug_exists(session, candidate):
            return candidate
        candidate = with_suffix(base)
    # 5 attempts failing is a real collision (bug or abuse). Surface it.
    raise PostError("could not allocate a unique slug; try a different title", code="slug_conflict")


async def create_post(
    session: AsyncSession,
    *,
    author: User,
    title: str,
    content: str,
    media_urls: list[str],
    status: PostStatus,
) -> Post:
    if not _can_use_status(author, status):
        raise PostError(
            f"role {author.role.value} may not publish or archive; save as draft",
            code="forbidden_status",
        )

    slug = await _unique_slug(session, title)
    try:
        post = await posts_repo.create_post(
            session,
            author_id=author.id,
            title=title,
            slug=slug,
            content=content,
            media_urls=media_urls,
            status=status,
        )
        await session.commit()
        await session.refresh(post)
        return post
    except IntegrityError as e:
        await session.rollback()
        raise PostError("slug collision; retry", code="slug_conflict") from e


async def get_post_or_404(
    session: AsyncSession, *, post_id: uuid.UUID, viewer: User | None
) -> Post:
    post = await posts_repo.get_by_id(session, post_id)
    if post is None or not _can_view(viewer, post):
        # Return "not found" (not "forbidden") to avoid leaking post existence.
        raise PostError("post not found", code="not_found")
    return post


async def get_post_by_slug_or_404(session: AsyncSession, *, slug: str, viewer: User | None) -> Post:
    post = await posts_repo.get_by_slug(session, slug)
    if post is None or not _can_view(viewer, post):
        raise PostError("post not found", code="not_found")
    return post


async def update_post(
    session: AsyncSession,
    *,
    post: Post,
    actor: User,
    title: str | None,
    content: str | None,
    media_urls: list[str] | None,
    status: PostStatus | None,
) -> Post:
    if not _can_edit(actor, post):
        raise PostError("you cannot edit this post", code="forbidden")

    if status is not None and status != post.status:
        if not _can_use_status(actor, status):
            raise PostError(
                f"role {actor.role.value} may not set status to {status.value}",
                code="forbidden_status",
            )
        post.status = status

    if title is not None and title != post.title:
        post.title = title
        # Only regenerate slug when title actually changed.
        new_slug = await _unique_slug(session, title)
        post.slug = new_slug

    if content is not None:
        post.content = content

    if media_urls is not None:
        post.media_urls = media_urls

    try:
        await session.commit()
        await session.refresh(post)
        return post
    except IntegrityError as e:
        await session.rollback()
        raise PostError("slug collision; retry", code="slug_conflict") from e


async def delete_post(session: AsyncSession, *, post: Post, actor: User) -> None:
    if not _can_delete(actor, post):
        raise PostError("you cannot delete this post", code="forbidden")
    await session.delete(post)
    await session.commit()
