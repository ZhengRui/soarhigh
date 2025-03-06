'use client';

import React from 'react';
import { useParams, useRouter } from 'next/navigation';
import { MeetingForm } from '../../MeetingForm';
import { MeetingAwardsForm } from '../../MeetingAwardsForm';
import { useMeeting } from '@/hooks/useMeeting';
import { Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { convertSegmentsToBaseSegments } from '@/utils/segments';

export default function EditMeetingPage() {
  const params = useParams();
  const router = useRouter();
  const meetingId = Array.isArray(params.id) ? params.id[0] : params.id || '';

  // Fetch the meeting data only if we have a valid meetingId
  const { data: meeting, isLoading, isError, error } = useMeeting(meetingId);

  // Handle loading state
  if (isLoading) {
    return (
      <div className='flex flex-col items-center justify-center min-h-[80vh] p-8'>
        <Loader2 className='w-8 h-8 text-blue-500 animate-spin mb-4' />
        <p className='text-gray-600'>Loading meeting data...</p>
      </div>
    );
  }

  // Handle error state
  if (isError) {
    const errorMessage =
      error instanceof Error ? error.message : 'Failed to load meeting';

    // Show toast error
    toast.error(errorMessage);

    // Redirect back to meetings list after a short delay
    setTimeout(() => {
      router.push('/meetings');
    }, 1500);

    return (
      <div className='flex flex-col items-center justify-center min-h-[80vh] p-8'>
        <p className='text-red-500 mb-2'>Error loading meeting data</p>
        <p className='text-gray-600'>Redirecting to meetings list...</p>
      </div>
    );
  }

  // Handle meeting not found
  if (!meeting) {
    toast.error('Meeting not found');

    // Redirect back to meetings list after a short delay
    setTimeout(() => {
      router.push('/meetings');
    }, 1500);

    return (
      <div className='flex flex-col items-center justify-center min-h-[80vh] p-8'>
        <p className='text-red-500 mb-2'>Meeting not found</p>
        <p className='text-gray-600'>Redirecting to meetings list...</p>
      </div>
    );
  }

  // Convert meeting.segments from SegmentIF[] to BaseSegment[]
  const convertedMeeting = {
    ...meeting,
    segments: convertSegmentsToBaseSegments(meeting.segments),
  };

  return (
    <div className='min-h-screen bg-gray-50 py-12'>
      <div className='container max-w-4xl mx-auto px-4'>
        <div className='bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-6'>
          <MeetingForm
            initFormData={convertedMeeting}
            mode='edit'
            meetingId={meetingId}
          />
        </div>

        {/* Meeting Awards Section */}
        <div className='bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden'>
          <MeetingAwardsForm meetingId={meetingId} />
        </div>
      </div>
    </div>
  );
}
