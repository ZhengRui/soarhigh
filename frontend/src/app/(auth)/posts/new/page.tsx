'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, PlusCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { MarkdownEditor } from '@/components/posts/MarkdownEditor';
import { createPost } from '@/utils/posts';

export default function NewPostPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isPublic, setIsPublic] = useState(false);

  const createPostMutation = useMutation({
    mutationFn: createPost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] });
      toast.success('Post created successfully!');
      router.push('/posts');
    },
    onError: (error) => {
      toast.error(
        `Failed to create post: ${error instanceof Error ? error.message : String(error)}`
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

    createPostMutation.mutate({
      title: title.trim(),
      content,
      is_public: isPublic,
    });
  };

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-5xl mx-auto'>
        <button
          onClick={() => router.back()}
          className='mb-8 flex items-center text-gray-600 hover:text-gray-900'
        >
          <ArrowLeft className='w-4 h-4 mr-1' />
          Back to Posts
        </button>

        <div className='bg-white shadow-sm rounded-lg overflow-hidden'>
          <form onSubmit={handleSubmit}>
            <div className='p-6'>
              <h1 className='text-2xl font-bold text-gray-900 mb-6'>
                Create New Post
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

            <div className='px-6 ext-right'>
              <div className='py-6 border-t border-gray-200'>
                <button
                  type='submit'
                  disabled={createPostMutation.isPending}
                  className='w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed'
                >
                  {createPostMutation.isPending ? (
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
                      <PlusCircle className='w-4 h-4' />
                      Create Post
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
