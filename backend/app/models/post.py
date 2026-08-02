from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Author(BaseModel):
    name: str = Field(description="The name of the author.")
    member_id: str = Field(description="The member ID of the author.")


class Post(BaseModel):
    """
    Model representing a blog post.
    """

    id: Optional[str] = Field(default=None, description="The unique identifier of the post.")
    title: str = Field(description="The title of the post.")
    slug: str = Field(description="The URL-friendly slug for the post.")
    content: str = Field(description="The markdown content of the post.")
    is_public: bool = Field(default=False, description="Whether the post is publicly viewable.")
    created_at: Optional[str] = Field(default=None, description="The timestamp when the post was created.")
    updated_at: Optional[str] = Field(default=None, description="The timestamp when the post was last updated.")
    author: Optional[Author] = Field(default=None, description="The author of the post.")


class ContentAuthor(BaseModel):
    name: str
    member_id: Optional[str] = None


class ContentListItem(BaseModel):
    """Shared card data for ordinary Posts and public WxPosts."""

    kind: Literal["post", "wxpost"]
    id: str
    title: str
    slug: str
    excerpt: Optional[str] = None
    author: ContentAuthor
    is_public: bool
    cover_image_url: Optional[str] = None
    article_revision: Optional[int] = None
    created_at: str


class PaginatedContentItems(BaseModel):
    items: List[ContentListItem]
    total: int
    page: int
    page_size: int
    pages: int
