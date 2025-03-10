'use client';

import React, { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Edit, Globe, Lock, Calendar, User } from 'lucide-react';
import Link from 'next/link';
import toast from 'react-hot-toast';
import { MarkdownRenderer } from '@/components/posts/MarkdownRenderer';
import { useAuth } from '@/hooks/useAuth';
import { usePost } from '@/hooks/usePost';

export default function PostPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params?.slug as string;
  const { data: user } = useAuth();

  const { data: post, isLoading, error } = usePost(slug);

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
              </div>

              <div className='flex flex-col xs:flex-row gap-2 xs:gap-4 items-start xs:items-center text-sm text-gray-500 mb-8'>
                <div className='flex items-center'>
                  <Calendar className='w-4 h-4 mr-1' />
                  <span>{formatDate(post.created_at)}</span>
                </div>

                <div className='flex items-center'>
                  <User className='w-4 h-4 mr-1' />
                  <span>{post.author.name}</span>
                </div>

                <div className='flex items-center'>
                  {post.is_public ? (
                    <Globe className='w-4 h-4 mr-1' />
                  ) : (
                    <Lock className='w-4 h-4 mr-1' />
                  )}
                  <span>{post.is_public ? 'Public' : 'Private'}</span>
                </div>
              </div>

              <div className='prose max-w-none'>
                <MarkdownRenderer content={post.content} />
              </div>

              {user && (
                <div className='mt-8 pt-6 border-t border-gray-200'>
                  <Link
                    href={`/posts/edit/${post.slug}`}
                    className='inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md'
                  >
                    <Edit className='w-4 h-4' />
                    <span className='font-medium'>Edit Post</span>
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
