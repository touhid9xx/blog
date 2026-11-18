import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PostStatus


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    media_urls: list[str] = Field(default_factory=list)
    status: PostStatus = PostStatus.DRAFT


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    media_urls: list[str] | None = None
    status: PostStatus | None = None


class PostPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    title: str
    slug: str
    content: str
    media_urls: list[str]
    status: PostStatus
    created_at: datetime
    updated_at: datetime


class PostListItem(BaseModel):
    """Lighter payload for list endpoints — omits full content."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    title: str
    slug: str
    status: PostStatus
    created_at: datetime
    updated_at: datetime


class PostListResponse(BaseModel):
    items: list[PostListItem]
    total: int
    page: int
    page_size: int
