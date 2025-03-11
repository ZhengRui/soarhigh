'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, Loader2, PenSquare, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { MarkdownEditor } from '@/components/posts/MarkdownEditor';
import { updatePost, deletePost } from '@/utils/posts';
import { useAuth } from '@/hooks/useAuth';
import { usePost } from '@/hooks/usePost';
import { useIsAdmin } from '@/hooks/useIsAdmin';

import Link from 'next/link';
import slugify from 'slugify';

export default function EditPostPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user } = useAuth();
  const { data: isAdmin } = useIsAdmin();
  const slug = params?.slug as string;

  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Fetch the post data
  const { data: post, isLoading, error } = usePost(slug);

  // Determine if current user can delete the post (author or admin)
  const canDeletePost = isAdmin || user?.uid === post?.author.member_id;

  // Check if user has permission and load data once fetched
  useEffect(() => {
    if (error) {
      toast.error(
        "Failed to load post. It may have been deleted or you don't have permission to edit it."
      );
      router.push('/posts');
      return;
    }

    if (post && initialLoad) {
      // Load post data into form
      setTitle(post.title);
      setContent(post.content);
      setIsPublic(post.is_public);
      setInitialLoad(false);
    }
  }, [post, user, slug, router, error, initialLoad]);

  const updatePostMutation = useMutation({
    mutationFn: updatePost,
    onSuccess: (updatedPost) => {
      // Remove the query for the old slug from cache completely
      queryClient.removeQueries({ queryKey: ['post', slug] });

      // Invalidate the posts list
      queryClient.invalidateQueries({ queryKey: ['posts'] });

      // Update URL path to reflect the new slug without full page refresh
      const newSlug = updatedPost.slug;
      if (newSlug && newSlug !== slug) {
        // Set the data for the new slug directly in the cache
        queryClient.setQueryData(['post', newSlug], updatedPost);

        // Update the URL to the new slug
        router.replace(`/posts/edit/${newSlug}`);
      }

      toast.success('Post updated successfully!');
    },
    onError: (error) => {
      toast.error(
        `Failed to update post: ${error instanceof Error ? error.message : String(error)}`
      );
    },
  });

  const deletePostMutation = useMutation({
    mutationFn: deletePost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] });
      toast.success('Post deleted successfully!');
      router.push('/posts');
    },
    onError: (error) => {
      toast.error(
        `Failed to delete post: ${error instanceof Error ? error.message : String(error)}`
      );
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!title.trim()) {
      toast.error('Please enter a title for your post');
      return;
    }

    if (!content.trim()) {
      toast.error('Please enter some content for your post');
      return;
    }

    updatePostMutation.mutate({
      id: post?.id,
      title: title.trim(),
      slug: slugify(title.trim(), { lower: true }),
      content,
      is_public: isPublic,
    });
  };

  // Show loading state
  if (isLoading) {
    return (
      <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8 flex items-center justify-center'>
        <div className='text-center'>
          <Loader2 className='w-12 h-12 text-blue-600 animate-spin mx-auto' />
          <p className='mt-4 text-gray-600'>Loading post...</p>
        </div>
      </div>
    );
  }

  const handleDeleteClick = () => {
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = () => {
    deletePostMutation.mutate(slug);
    setShowDeleteConfirm(false);
  };

  const handleDeleteCancel = () => {
    setShowDeleteConfirm(false);
  };

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-5xl mx-auto'>
        <Link
          href={`/posts/${slug}`}
          className='mb-8 flex items-center text-gray-600 hover:text-gray-900'
        >
          <ArrowLeft className='w-4 h-4 mr-1' />
          Back to Post
        </Link>

        <div className='bg-white shadow-sm rounded-lg overflow-hidden'>
          <form onSubmit={handleSubmit}>
            <div className='p-6 border-b border-gray-200'>
              <div className='flex justify-between items-center mb-6'>
                <div>
                  <h1 className='text-2xl font-semibold text-gray-900 flex items-center'>
                    <PenSquare className='w-5 h-5 mr-2 text-indigo-500' />
                    Edit Post
                  </h1>
                  <p className='mt-1 text-sm text-gray-600'>
                    Update your post details
                  </p>
                </div>

                {/* Delete button - only shown if user can delete (author or admin) */}
                {canDeletePost && (
                  <button
                    type='button'
                    disabled={deletePostMutation.isPending}
                    onClick={handleDeleteClick}
                    className='flex items-center justify-center gap-1.5 p-3 rounded-full sm:py-1.5 sm:px-3 sm:rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed'
                  >
                    {deletePostMutation.isPending ? (
                      <Loader2 className='w-4 h-4 animate-spin' />
                    ) : (
                      <Trash2 className='w-4 h-4' />
                    )}
                    <span className='hidden sm:block'>Delete Post</span>
                  </button>
                )}
              </div>

              <div className='mb-6'>
                <label
                  htmlFor='title'
                  className='block text-sm font-medium text-gray-700 mb-1'
                >
                  Title
                </label>
                <input
                  type='text'
                  id='title'
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder='Enter post title'
                  className='w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500'
                  required
                />
              </div>

              <div>
                <label className='block text-sm font-medium text-gray-700 mb-1'>
                  Content
                </label>
                <MarkdownEditor
                  initialValue={content}
                  onChange={setContent}
                  isPublic={isPublic}
                  onVisibilityChange={setIsPublic}
                />
              </div>
            </div>

            <div className='px-6 text-right'>
              <div className='py-6 border-t border-gray-200'>
                <button
                  type='submit'
                  disabled={updatePostMutation.isPending}
                  className='w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed'
                >
                  {updatePostMutation.isPending ? (
                    <>
                      <div className='animate-spin h-4 w-4'>
                        <svg
                          className='w-full h-full'
                          xmlns='http://www.w3.org/2000/svg'
                          fill='none'
                          viewBox='0 0 24 24'
                        >
                          <circle
                            className='opacity-25'
                            cx='12'
                            cy='12'
                            r='10'
                            stroke='currentColor'
                            strokeWidth='4'
                          ></circle>
                          <path
                            className='opacity-75'
                            fill='currentColor'
                            d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z'
                          ></path>
                        </svg>
                      </div>
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className='w-4 h-4' />
                      Save Post
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div className='fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50'>
          <div className='bg-white rounded-lg p-6 max-w-md mx-auto'>
            <h3 className='text-lg font-semibold text-gray-900 mb-2'>
              Confirm Delete
            </h3>
            <p className='text-gray-700 mb-4'>
              Are you sure you want to delete this post? This action cannot be
              undone.
            </p>
            <div className='flex justify-end gap-3'>
              <button
                type='button'
                onClick={handleDeleteCancel}
                className='px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200'
              >
                Cancel
              </button>
              <button
                type='button'
                onClick={handleDeleteConfirm}
                className='px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700'
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
