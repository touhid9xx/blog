import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user
from app.db.session import get_session
from app.models.enums import PostStatus, UserRole
from app.models.post import Post
from app.models.user import User
from app.schemas.posts import (
    PostCreate,
    PostListItem,
    PostListResponse,
    PostPublic,
    PostUpdate,
)
from app.services import posts_repo, posts_service
from app.services.posts_service import PostError

router = APIRouter(prefix="/posts", tags=["posts"])


def _map_post_error(e: PostError) -> HTTPException:
    mapping = {
        "not_found": status.HTTP_404_NOT_FOUND,
        "forbidden": status.HTTP_403_FORBIDDEN,
        "forbidden_status": status.HTTP_403_FORBIDDEN,
        "slug_conflict": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        status_code=mapping.get(e.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": e.code, "message": e.message},
    )


# ── Public / Optional-Auth Reads ────────────────────────────────


@router.get("", response_model=PostListResponse)
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: PostStatus | None = Query(None, alias="status"),
    author_id: uuid.UUID | None = Query(None),
    viewer: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> PostListResponse:
    """
    Public list. Anonymous viewers see only PUBLISHED.
    Authenticated users additionally see their own drafts (customers)
    or all statuses (editors/admins) when `status` is passed.
    """
    effective_status: PostStatus | None
    if viewer is None:
        effective_status = PostStatus.PUBLISHED
    elif viewer.role in (UserRole.ADMIN, UserRole.EDITOR):
        effective_status = status_filter
    else:
        if status_filter == PostStatus.PUBLISHED:
            effective_status = PostStatus.PUBLISHED
            author_id = None
        elif status_filter in (PostStatus.DRAFT, PostStatus.ARCHIVED):
            author_id = viewer.id
            effective_status = status_filter
        else:
            effective_status = PostStatus.PUBLISHED

    items, total = await posts_repo.list_posts(
        session,
        page=page,
        page_size=page_size,
        status=effective_status,
        author_id=author_id,
    )
    return PostListResponse(
        items=[PostListItem.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# MUST be placed BEFORE /{post_id} to prevent "by-slug" being parsed as a UUID
@router.get("/by-slug/{slug}", response_model=PostPublic)
async def get_post_by_slug(
    slug: str,
    viewer: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> PostPublic:
    try:
        post = await posts_service.get_post_by_slug_or_404(session, slug=slug, viewer=viewer)
    except PostError as e:
        raise _map_post_error(e) from e
    return PostPublic.model_validate(post)


@router.get("/{post_id}", response_model=PostPublic)
async def get_post(
    post_id: uuid.UUID,
    viewer: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> PostPublic:
    try:
        post = await posts_service.get_post_or_404(session, post_id=post_id, viewer=viewer)
    except PostError as e:
        raise _map_post_error(e) from e
    return PostPublic.model_validate(post)


# ── Authenticated Mutators ──────────────────────────────────────


@router.post("", response_model=PostPublic, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PostPublic:
    try:
        post: Post = await posts_service.create_post(
            session,
            author=current_user,
            title=body.title,
            content=body.content,
            media_urls=body.media_urls,
            status=body.status,
        )
    except PostError as e:
        raise _map_post_error(e) from e
    return PostPublic.model_validate(post)


@router.patch("/{post_id}", response_model=PostPublic)
async def update_post(
    post_id: uuid.UUID,
    body: PostUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PostPublic:
    try:
        post = await posts_service.get_post_or_404(session, post_id=post_id, viewer=current_user)
        post = await posts_service.update_post(
            session,
            post=post,
            actor=current_user,
            title=body.title,
            content=body.content,
            media_urls=body.media_urls,
            status=body.status,
        )
    except PostError as e:
        raise _map_post_error(e) from e
    return PostPublic.model_validate(post)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        post = await posts_service.get_post_or_404(session, post_id=post_id, viewer=current_user)
        await posts_service.delete_post(session, post=post, actor=current_user)
    except PostError as e:
        raise _map_post_error(e) from e
