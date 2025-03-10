'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { MarkdownEditor } from '@/components/posts/MarkdownEditor';
import { getPost, updatePost } from '@/utils/posts';
import { useAuth } from '@/hooks/useAuth';

export default function EditPostPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user } = useAuth();
  const slug = params?.slug as string;

  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);

  // Fetch the post data
  const {
    data: post,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['post', slug],
    queryFn: () => getPost(slug),
    retry: false,
  });

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
      // Check if user has permission to edit this post
      if (user?.uid !== post.author_id) {
        toast.error("You don't have permission to edit this post");
        router.push(`/posts/${slug}`);
        return;
      }

      // Load post data into form
      setTitle(post.title);
      setContent(post.content);
      setIsPublic(post.is_public);
      setInitialLoad(false);
    }
  }, [post, user, slug, router, error, initialLoad]);

  const updatePostMutation = useMutation({
    mutationFn: (data: {
      title: string;
      content: string;
      is_public: boolean;
    }) => updatePost(slug, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] });
      queryClient.invalidateQueries({ queryKey: ['post', slug] });
      toast.success('Post updated successfully!');
      router.push(`/posts/${slug}`);
    },
    onError: (error) => {
      toast.error(
        `Failed to update post: ${error instanceof Error ? error.message : String(error)}`
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
      title: title.trim(),
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

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-5xl mx-auto'>
        <button
          onClick={() => router.back()}
          className='mb-8 flex items-center text-gray-600 hover:text-gray-900'
        >
          <ArrowLeft className='w-4 h-4 mr-1' />
          Back to Post
        </button>

        <div className='bg-white shadow-sm rounded-lg overflow-hidden'>
          <form onSubmit={handleSubmit}>
            <div className='p-6 border-b border-gray-200'>
              <h1 className='text-2xl font-bold text-gray-900 mb-6'>
                Edit Post
              </h1>

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

            <div className='px-6 py-4 bg-gray-50 text-right'>
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
          </form>
        </div>
      </div>
    </div>
  );
}
