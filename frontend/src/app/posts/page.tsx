'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Edit, Globe, Lock, Plus, CalendarDays, Loader2 } from 'lucide-react';
import { getPosts } from '@/utils/posts';
import { useAuth } from '@/hooks/useAuth';
import type { Post } from '@/utils/posts';

export default function PostsPage() {
  const { data: user } = useAuth();
  const [filter, setFilter] = useState<'all' | 'public' | 'private'>('all');

  const { data: posts = [], isLoading } = useQuery({
    queryKey: ['posts'],
    queryFn: getPosts,
  });

  // Filter posts based on the selected filter
  const filteredPosts = posts.filter((post: Post) => {
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
        {isLoading && (
          <div className='flex flex-col min-h-[70vh] items-center justify-center py-12'>
            <Loader2 className='w-8 h-8 text-blue-500 animate-spin mb-4' />
            {/* <p className='text-gray-600'>Loading posts...</p> */}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && filteredPosts.length === 0 && (
          <div className='flex justify-center items-center min-h-[70vh] py-12'>
            <div className='text-center'>
              <p className='text-gray-500 mb-4'>No posts found</p>
              {user && (
                <Link
                  href='/posts/new'
                  className='inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md'
                >
                  <Plus className='w-4 h-4' />
                  <span className='font-medium'>Create your first post</span>
                </Link>
              )}
            </div>
          </div>
        )}

        {/* Posts list */}
        {filteredPosts.length > 0 && (
          <div className='space-y-6'>
            {filteredPosts.map((post: Post) => (
              <Link
                key={post.id}
                href={`/posts/${post.slug}`}
                className='block bg-white rounded-lg shadow-sm hover:shadow-md transition-all duration-200'
              >
                <div className='p-5'>
                  <div className='flex justify-between items-start mb-2'>
                    <h2 className='text-xl font-semibold text-gray-900'>
                      {post.title}
                    </h2>
                    <div className='ml-3 flex-shrink-0'>
                      {post.is_public ? (
                        <span className='bg-green-100 text-green-800 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium'>
                          <Globe className='w-3 h-3 mr-1' />
                          Public
                        </span>
                      ) : (
                        <span className='bg-blue-100 text-blue-800 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium'>
                          <Lock className='w-3 h-3 mr-1' />
                          Private
                        </span>
                      )}
                    </div>
                  </div>

                  <p className='text-gray-600 text-sm line-clamp-2 mt-1'>
                    {post.content.replace(/[#*`]/g, '').slice(0, 150)}
                    {post.content.length > 150 ? '...' : ''}
                  </p>

                  <div className='flex justify-between items-center text-xs text-gray-500 mt-4'>
                    <div className='flex items-center gap-1'>
                      <CalendarDays className='w-3.5 h-3.5' />
                      <span>{formatDate(post.created_at)}</span>
                    </div>
                    {user && user.uid === post.author_id && (
                      <div className='flex items-center gap-1 text-blue-600'>
                        <Edit className='w-3.5 h-3.5' />
                        <span>Edit</span>
                      </div>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
