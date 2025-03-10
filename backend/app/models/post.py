from typing import List, Optional

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


class PaginatedPosts(BaseModel):
    """
    Model for paginated list of posts.
    """

    items: List[Post]
    total: int
    page: int
    page_size: int
    pages: int
