import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    CUSTOMER = "customer"


class PostStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
