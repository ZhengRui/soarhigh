'use client';

import { MeetingCard } from './MeetingCard';
import { Plus, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { useMeetings } from '@/hooks/useMeetings';
import { useState } from 'react';
import { Pagination } from '@/components/Pagination';

export default function MeetingsPage() {
  const { isPending: isAuthPending, data: user } = useAuth();

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Use the updated hook with pagination parameters
  const { isPending: isMeetingPending, data: paginatedMeetings } = useMeetings({
    page: currentPage,
    pageSize: pageSize,
  });

  // Extract meetings and pagination info
  const meetings = paginatedMeetings?.items || [];
  const totalPages = paginatedMeetings?.pages || 0;

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

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
          <div className='flex flex-col min-h-[70vh] items-center justify-center py-12'>
            <Loader2 className='w-8 h-8 text-blue-500 animate-spin mb-4' />
          </div>
        )}

        {/* Meetings list */}
        {!isMeetingPending && paginatedMeetings && (
          <>
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
                <div className='flex justify-center items-center min-h-[70vh] py-12'>
                  <p className='text-gray-500'>No meetings found</p>
                </div>
              )}
            </div>

            {/* Pagination component */}
            {meetings.length > 0 && (
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={handlePageChange}
              />
            )}

            {/* Pagination info */}
            {meetings.length > 0 && paginatedMeetings.total > 0 && (
              <div className='text-center text-sm text-gray-500 mt-4'>
                Showing{' '}
                {Math.min(
                  (currentPage - 1) * pageSize + 1,
                  paginatedMeetings.total
                )}{' '}
                to {Math.min(currentPage * pageSize, paginatedMeetings.total)}{' '}
                of {paginatedMeetings.total} meetings
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
