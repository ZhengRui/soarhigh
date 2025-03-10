'use client';

import React, { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Edit, Globe, Lock, Calendar, User } from 'lucide-react';
import Link from 'next/link';
import toast from 'react-hot-toast';
import { MarkdownRenderer } from '@/components/posts/MarkdownRenderer';
import { getPost } from '@/utils/posts';
import { useAuth } from '@/hooks/useAuth';

export default function PostPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params?.slug as string;
  const { data: user } = useAuth();

  const {
    data: post,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['post', slug],
    queryFn: () => getPost(slug),
    retry: false,
  });

  // Handle errors
  useEffect(() => {
    if (error) {
      if ((error as any)?.status === 404) {
        toast.error('Post not found');
        router.push('/posts');
      }
    }
  }, [error, router]);

  // Format date for display
  const formatDate = (dateString?: string) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(date);
  };

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-4xl mx-auto'>
        <Link
          href='/posts'
          className='mb-8 inline-flex items-center text-gray-600 hover:text-gray-900'
        >
          <ArrowLeft className='w-4 h-4 mr-1' />
          Back to Posts
        </Link>

        {isLoading && (
          <div className='text-center py-12'>
            <div className='inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent'></div>
            <p className='mt-4 text-gray-600'>Loading post...</p>
          </div>
        )}

        {error && (
          <div className='bg-red-50 border border-red-200 text-red-800 rounded-md p-4 my-4'>
            <p>
              Error loading post. The post may have been removed or you
              don&apos;t have permission to view it.
            </p>
          </div>
        )}

        {post && (
          <div className='bg-white shadow-sm rounded-lg overflow-hidden'>
            <div className='p-6 md:p-8'>
              <div className='flex justify-between items-start mb-6'>
                <h1 className='text-3xl font-bold text-gray-900'>
                  {post.title}
                </h1>

                <div className='flex items-center'>
                  {post.is_public ? (
                    <span className='bg-green-100 text-green-800 inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium'>
                      <Globe className='w-3 h-3 mr-1' />
                      Public
                    </span>
                  ) : (
                    <span className='bg-blue-100 text-blue-800 inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium'>
                      <Lock className='w-3 h-3 mr-1' />
                      Private
                    </span>
                  )}
                </div>
              </div>

              <div className='flex items-center text-sm text-gray-500 mb-8'>
                <div className='flex items-center mr-4'>
                  <Calendar className='w-4 h-4 mr-1' />
                  <span>{formatDate(post.created_at)}</span>
                </div>
                <div className='flex items-center'>
                  <User className='w-4 h-4 mr-1' />
                  <span>Author Name</span>{' '}
                  {/* This would need to be fetched from user data */}
                </div>
              </div>

              <div className='prose max-w-none'>
                <MarkdownRenderer content={post.content} />
              </div>

              {user && user.uid === post.author_id && (
                <div className='mt-8 pt-6 border-t border-gray-200'>
                  <Link
                    href={`/posts/edit/${post.slug}`}
                    className='inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'
                  >
                    <Edit className='w-4 h-4 mr-2 text-gray-500' />
                    Edit Post
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
