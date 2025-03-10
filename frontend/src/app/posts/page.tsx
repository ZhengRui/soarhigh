'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  Edit,
  Globe,
  Lock,
  Plus,
  CalendarDays,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { usePosts } from '@/hooks/usePosts';

export default function PostsPage() {
  const { data: user } = useAuth();
  const [filter, setFilter] = useState<'all' | 'public' | 'private'>('all');

  const {
    data: paginatedPosts,
    isPending: isPostsPending,
    isRefreshingInBackground,
  } = usePosts({
    page: 1,
    pageSize: 10,
  });

  // Extract posts array from the paginated response
  const posts = paginatedPosts?.items || [];

  // Filter posts based on the selected filter
  const filteredPosts = posts.filter((post) => {
    if (filter === 'all') return true;
    if (filter === 'public') return post.is_public;
    if (filter === 'private') return !post.is_public;
    return true;
  });

  // Format date for display
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(date);
  };

  return (
    <div className='min-h-screen bg-gray-50 py-12'>
      <div className='container max-w-4xl mx-auto px-4'>
        <div className='flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-8'>
          <div>
            <h1 className='text-3xl sm:text-4xl font-bold text-gray-900 mb-2 sm:mb-4'>
              Posts
            </h1>
            <p className='text-gray-600 text-sm sm:text-base'>
              Read and share knowledge with the SoarHigh community
            </p>
          </div>

          {user && (
            <Link
              href='/posts/new'
              className='self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md whitespace-nowrap'
            >
              <Plus className='w-4 h-4' />
              <span className='font-medium'>New Post</span>
            </Link>
          )}
        </div>

        {/* Filter controls - only show to authenticated users */}
        {user && (
          <div className='mb-6 flex flex-wrap gap-2'>
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                filter === 'all'
                  ? 'bg-gradient-to-r from-blue-50 to-purple-50 text-blue-700 border border-blue-200'
                  : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              All Posts
            </button>
            <button
              onClick={() => setFilter('public')}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                filter === 'public'
                  ? 'bg-green-50 text-green-700 border border-green-200'
                  : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              Public Posts
            </button>
            <button
              onClick={() => setFilter('private')}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                filter === 'private'
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              Private Posts
            </button>
          </div>
        )}

        {/* Loading state */}
        {isPostsPending && !paginatedPosts && (
          <div className='flex flex-col min-h-[70vh] items-center justify-center py-12'>
            <Loader2 className='w-8 h-8 text-blue-500 animate-spin mb-4' />
          </div>
        )}

        {/* Empty state */}
        {!isPostsPending && filteredPosts.length === 0 && (
          <div className='flex justify-center items-center min-h-[70vh] py-12'>
            <div className='text-center'>
              <p className='text-gray-500 mb-4'>No posts found</p>
              {/* {user && (
                <Link
                  href='/posts/new'
                  className='inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md'
                >
                  <Plus className='w-4 h-4' />
                  <span className='font-medium'>Create your first post</span>
                </Link>
              )} */}
            </div>
          </div>
        )}

        {/* Posts list */}
        {filteredPosts.length > 0 && (
          <div className='space-y-6'>
            {/* Background refresh indicator */}
            {isRefreshingInBackground && (
              <div className='flex items-center justify-center bg-blue-50 py-2 px-4 rounded-md mb-4'>
                <RefreshCw className='w-4 h-4 text-blue-500 animate-spin mr-2' />
                <span className='text-sm text-blue-600'>
                  Refreshing data...
                </span>
              </div>
            )}

            {filteredPosts.map((post) => (
              <div
                key={post.id}
                className='block bg-white rounded-lg shadow-sm hover:shadow-md transition-all duration-200'
              >
                <div className='p-5'>
                  <Link href={`/posts/${post.slug}`} className='block'>
                    <div className='mb-2'>
                      <h2 className='text-xl font-semibold text-gray-900'>
                        {post.title}
                      </h2>
                    </div>

                    <p className='text-gray-600 text-sm line-clamp-2 mt-1'>
                      {post.content.replace(/[#*`]/g, '').slice(0, 150)}
                      {post.content.length > 150 ? '...' : ''}
                    </p>
                  </Link>

                  <div className='flex justify-start gap-3 items-center text-xs text-gray-500 mt-4'>
                    <div className='flex items-center gap-1'>
                      <CalendarDays className='w-3.5 h-3.5' />
                      <span>{formatDate(post.created_at!)}</span>
                    </div>

                    <div className='flex-shrink-0'>
                      {post.is_public ? (
                        <span className='bg-green-100 text-green-800 inline-flex items-center p-1.5 sm:px-3 sm:py-0.5 rounded-full text-xs font-medium'>
                          <Globe className='w-3 h-3 sm:mr-1' />
                          <span className='hidden sm:inline'>Public</span>
                        </span>
                      ) : (
                        <span className='bg-red-100 text-red-800 inline-flex items-center p-1.5 sm:px-3 sm:py-0.5 rounded-full text-xs font-medium'>
                          <Lock className='w-3 h-3 sm:mr-1' />
                          <span className='hidden sm:inline'>Private</span>
                        </span>
                      )}
                    </div>

                    {user && (
                      <Link
                        href={`/posts/edit/${post.slug}`}
                        className='bg-indigo-100 text-indigo-800 inline-flex items-center p-1.5 sm:px-3 sm:py-0.5 rounded-full text-xs font-medium hover:shadow-md transition-all duration-200'
                      >
                        <Edit className='w-3.5 h-3.5 sm:mr-1' />
                        <span className='hidden sm:inline'>Edit</span>
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
