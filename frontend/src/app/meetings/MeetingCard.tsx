'use client';

import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Clock,
  MapPin,
  Trophy,
  PencilLine,
  Eye,
  EyeOff,
  Loader2,
} from 'lucide-react';
import { MeetingIF, AwardIF } from '@/interfaces';
import Link from 'next/link';
import { updateMeetingStatus } from '@/utils/meeting';
import toast from 'react-hot-toast';
import { useQueryClient } from '@tanstack/react-query';

type MeetingCardProps = {
  meeting: MeetingIF;
  isAuthenticated: boolean;
};

export const MeetingCard: React.FC<MeetingCardProps> = ({
  meeting,
  isAuthenticated,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  const queryClient = useQueryClient();

  // Destructure the meeting object
  const {
    id,
    meeting_type,
    theme,
    meeting_manager,
    date,
    start_time,
    end_time,
    location,
    introduction,
    segments,
    status,
  } = meeting;

  const mockAwards: AwardIF[] = [
    { category: 'Best Prepared Speaker', winner: 'Frank Chen' },
    { category: 'Best Host', winner: 'Jessica Wang' },
    { category: 'Best Table Topic Speaker', winner: 'Emily Liu' },
    { category: 'Best Facilitator', winner: 'Max Zhang' },
    { category: 'Best Evaluator', winner: 'Amanda Wu' },
    { category: 'Best Supporter', winner: 'Joyce Li' },
  ];

  // Check if the meeting date has passed
  // const hasPassed = new Date(date) < new Date();
  const hasPassed = true;

  const handlePublishToggle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!id || !isAuthenticated || isToggling) return;

    setIsToggling(true);
    try {
      const newStatus = status === 'published' ? 'draft' : 'published';
      await updateMeetingStatus(id, newStatus);

      // Immediately update the local meeting state with the new status
      // This ensures the eye icon updates immediately without waiting for the query refetch
      meeting.status = newStatus;

      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['meetings'] });

      toast.success(
        newStatus === 'published'
          ? 'Meeting published successfully!'
          : 'Meeting unpublished successfully!'
      );
    } catch (err) {
      console.error('Error toggling meeting status:', err);
      toast.error(
        err instanceof Error ? err.message : 'Failed to update meeting status'
      );
    } finally {
      setIsToggling(false);
    }
  };

  return (
    <div className='bg-white rounded-xl shadow-lg overflow-hidden transition-all duration-200 ease-in-out hover:shadow-xl border border-[#e5e7eb]'>
      <div
        className='p-6 cursor-pointer group relative'
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className='flex justify-between items-start mb-4'>
          <div>
            <div className='flex items-center gap-2'>
              <span className='px-4 py-1 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-full text-sm font-medium'>
                {meeting_type}
              </span>

              {isAuthenticated && id && (
                <>
                  <button
                    onClick={handlePublishToggle}
                    disabled={isToggling}
                    className={`rounded-full p-1.5 transition-colors bg-gray-100 text-gray-400 ${
                      status === 'published'
                        ? 'group-hover:bg-emerald-50 group-hover:text-emerald-500'
                        : 'group-hover:bg-red-50 group-hover:text-red-500'
                    }`}
                    title={
                      status === 'published'
                        ? 'Unpublish meeting'
                        : 'Publish meeting'
                    }
                  >
                    {isToggling ? (
                      <Loader2 className='w-4 h-4 animate-spin' />
                    ) : status === 'published' ? (
                      <Eye className='w-4 h-4' />
                    ) : (
                      <EyeOff className='w-4 h-4' />
                    )}
                  </button>

                  <Link
                    href={`/meetings/edit/${id}`}
                    className='rounded-full p-1.5 bg-gray-100 group-hover:bg-indigo-50 transition-colors'
                    onClick={(e) => e.stopPropagation()}
                    title='Edit meeting'
                  >
                    <PencilLine className='w-4 h-4 text-gray-400 group-hover:text-indigo-500 transition-colors' />
                  </Link>
                </>
              )}
            </div>

            <h2 className='text-2xl font-bold mt-3 text-gray-800'>{theme}</h2>
            <p className='text-gray-500 mt-1 text-sm'>
              Managed by {meeting_manager}
            </p>
          </div>

          {isExpanded ? (
            <ChevronUp className='w-5 h-5 text-gray-400' />
          ) : (
            <ChevronDown className='w-5 h-5 text-gray-400' />
          )}
        </div>

        <div className='flex flex-col gap-2 text-gray-500 text-sm'>
          <p className='flex items-center gap-2'>
            <Clock className='min-w-4 min-h-4 w-4 h-4' />
            {date} | {start_time} - {end_time}
          </p>
          <p className='flex items-center gap-2'>
            <MapPin className='min-w-4 min-h-4 w-4 h-4' />
            {location}
          </p>
        </div>

        <p className='mt-4 text-sm text-gray-500 leading-relaxed'>
          {introduction}
        </p>

        {hasPassed && (
          <div className='mt-6 pt-6 border-t border-dashed border-gray-300'>
            <div className='flex items-center gap-2 mb-3'>
              <Trophy className='w-4 h-4 text-indigo-600' />
              <h3 className='text-sm font-semibold text-gray-800'>
                Meeting Awards
              </h3>
            </div>
            <div className='grid grid-cols-2 md:grid-cols-3 gap-4'>
              {mockAwards.map((award, index) => (
                <div key={index} className='text-sm'>
                  <p className='text-gray-500 font-medium'>{award.category}</p>
                  <p className='text-indigo-600'>{award.winner}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isExpanded ? 'max-h-[4000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className='p-6 border-t border-gray-300 bg-gradient-to-b from-white to-[#F9FAFB]'>
          <h3 className='text-lg font-semibold mb-4 text-gray-800'>
            Meeting Schedule
          </h3>
          <div className='space-y-6 sm:space-y-4'>
            {segments.map((segment) => (
              <div
                key={segment.segment_id}
                className='flex flex-col sm:flex-row gap-1 sm:gap-4 relative mb-4'
              >
                <div className='w-full sm:pt-1 sm:w-24 flex-shrink-0 flex sm:flex-col items-center sm:items-start justify-between'>
                  <div className='flex sm:flex-col items-center sm:items-start gap-2 sm:gap-0'>
                    <span className='text-sm font-medium text-indigo-600'>
                      {segment.start_time}
                    </span>
                    <span className='text-xs text-gray-500'>
                      {segment.duration}min
                    </span>
                  </div>
                </div>
                <div className='flex-grow'>
                  <div className='flex flex-col'>
                    <h4 className='font-medium text-gray-800'>
                      {segment.segment_type}
                    </h4>
                    <p className='text-sm text-gray-500'>
                      {segment.role_taker}
                      {segment.title && ` - ${segment.title}`}
                    </p>
                  </div>
                </div>
                <div className='hidden sm:block absolute left-24 top-0 bottom-0 w-0.5 bg-gradient-to-b from-indigo-600 to-purple-600 -z-10' />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
