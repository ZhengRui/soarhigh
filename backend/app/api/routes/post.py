from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ...db.core import (
    create_post,
    delete_post,
    get_post_by_slug,
    get_posts,
    update_post,
)
from ...models.post import PaginatedPosts, Post
from ...models.users import User
from .auth import get_current_user, get_optional_user

post_router = r = APIRouter()


@r.get("/posts", response_model=PaginatedPosts)
async def r_list_posts(
    user: Optional[User] = Depends(get_optional_user),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
) -> PaginatedPosts:
    """
    Get a paginated list of posts.

    Anonymous users can only see public posts.
    Authenticated users can see all posts.
    """
    user_id = user.uid if user else None
    result = get_posts(user_id=user_id, page=page, page_size=page_size)
    return PaginatedPosts(**result)


@r.get("/posts/{slug}", response_model=Post)
async def r_get_post(
    slug: str = Path(..., description="The slug of the post to retrieve"),
    user: Optional[User] = Depends(get_optional_user),
) -> Post:
    """
    Get a specific post by its slug.

    Anonymous users can only access public posts.
    Authenticated users can access all posts.
    """
    user_id = user.uid if user else None
    post = get_post_by_slug(slug=slug, user_id=user_id)

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return Post(**post)


@r.post("/posts", response_model=Post)
async def r_create_post(post_data: Post, user: User = Depends(get_current_user)) -> Post:
    """
    Create a new post.

    Requires authentication.
    """
    # Convert Pydantic model to dict
    post_dict = post_data.dict(exclude_unset=True, exclude={"author"})

    # Create the post
    result = create_post(post_dict, user_id=user.uid)

    if not result:
        raise HTTPException(status_code=500, detail="Failed to create post")

    return Post(**result)


@r.patch("/posts/{slug}", response_model=Post)
async def r_update_post(
    post_data: Post,
    slug: str = Path(..., description="The slug of the post to update"),
    user: User = Depends(get_current_user),
) -> Post:
    """
    Update an existing post.

    Requires authentication.
    Only the author can update their own posts.
    """
    # Convert Pydantic model to dict
    post_dict = post_data.dict(exclude_unset=True, exclude={"author"})

    # Update the post
    result = update_post(slug=slug, post_data=post_dict, user_id=user.uid)

    if not result:
        raise HTTPException(status_code=404, detail="Post not found or you don't have permission to update it")

    return Post(**result)


@r.delete("/posts/{slug}")
async def r_delete_post(
    slug: str = Path(..., description="The slug of the post to delete"), user: User = Depends(get_current_user)
):
    """
    Delete an existing post.

    Requires authentication.
    Only the author can delete their own posts.
    """
    # Delete the post
    success = delete_post(slug=slug, user_id=user.uid)

    if not success:
        raise HTTPException(status_code=404, detail="Post not found or you don't have permission to delete it")

    return {"message": "Post deleted successfully"}
