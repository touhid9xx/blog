import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import PostStatus

if TYPE_CHECKING:
    from app.models.user import User


def _post_status_values(enum_cls: type[PostStatus]) -> list[str]:
    return [member.value for member in enum_cls]


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[PostStatus] = mapped_column(
        SAEnum(
            PostStatus,
            name="post_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=PostStatus.DRAFT,
        server_default=PostStatus.DRAFT.value,
        nullable=False,
        index=True,
    )

    author: Mapped["User"] = relationship(back_populates="posts")
