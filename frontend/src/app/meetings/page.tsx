'use client';

import { MeetingCard } from './MeetingCard';
import { Plus, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { useMeetings } from '@/hooks/useMeetings';

export default function MeetingsPage() {
  const { isPending: isAuthPending, data: user } = useAuth();
  const { isPending: isMeetingPending, data: meetings } = useMeetings();

  return (
    <div className='min-h-screen bg-gray-50 py-12'>
      <div className='container max-w-4xl mx-auto px-4'>
        <div className='flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-8'>
          <div>
            <h1 className='text-3xl sm:text-4xl font-bold text-gray-900 mb-2 sm:mb-4'>
              Recent Meetings
            </h1>
            <p className='text-gray-600 text-sm sm:text-base'>
              Join our weekly meetings to practice and improve your public
              speaking skills.
            </p>
          </div>

          {!isAuthPending && user && (
            <Link
              href='/meetings/new'
              className='self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md whitespace-nowrap'
            >
              <Plus className='w-4 h-4' />
              <span className='font-medium'>Create Meeting</span>
            </Link>
          )}
        </div>

        {/* Loading state */}
        {isMeetingPending && (
          <div className='flex flex-col items-center justify-center py-12'>
            <Loader2 className='w-8 h-8 text-blue-500 animate-spin mb-4' />
            <p className='text-gray-600'>Loading meetings...</p>
          </div>
        )}

        {/* Meetings list */}
        {!isMeetingPending && meetings && (
          <div className='space-y-6'>
            {meetings.length > 0 ? (
              meetings.map((meeting) => (
                <MeetingCard
                  key={meeting.id}
                  meeting={meeting}
                  isAuthenticated={!!user}
                />
              ))
            ) : (
              <div className='text-center py-12'>
                <p className='text-gray-500'>No meetings found</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
