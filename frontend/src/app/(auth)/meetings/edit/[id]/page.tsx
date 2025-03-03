'use client';

import React from 'react';
import { useParams, useRouter } from 'next/navigation';
import { MeetingForm } from '../../MeetingForm';
import { useMeeting } from '@/hooks/useMeeting';
import { Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { SegmentIF } from '@/interfaces';
import {
  BaseSegment,
  CustomSegment,
  SEGMENT_TYPE_MAP,
  SegmentParams,
} from '../../default';

/**
 * Converts a SegmentIF array to BaseSegment array
 * This is necessary because MeetingForm expects BaseSegment objects
 * with config properties that the API doesn't include
 */
function convertSegmentsToBaseSegments(segments: SegmentIF[]): BaseSegment[] {
  return segments.map((segment) => {
    const params: SegmentParams = {
      id: segment.id,
      start_time: segment.start_time,
      duration: segment.duration,
      related_segment_ids: segment.related_segment_ids,
    };

    // Try to find a matching segment type class
    const segmentType = segment.type;

    // Check if it's a prepared speech (which might have a number)
    if (
      segmentType.startsWith('Prepared Speech') &&
      !segmentType.includes('Evaluation')
    ) {
      return new SEGMENT_TYPE_MAP['Prepared Speech'](params);
    }

    // Check if it's a prepared speech evaluation
    if (
      segmentType.startsWith('Prepared Speech') &&
      segmentType.includes('Evaluation')
    ) {
      return new SEGMENT_TYPE_MAP['Prepared Speech Evaluation'](params);
    }

    // For other segment types, look up in the map
    const SegmentClass =
      SEGMENT_TYPE_MAP[segmentType as keyof typeof SEGMENT_TYPE_MAP];

    // If we found a matching class, use it, otherwise create a custom segment
    if (SegmentClass) {
      const baseSegment = new SegmentClass(params);

      // Copy over any existing values
      if (segment.role_taker) baseSegment.role_taker = segment.role_taker;
      if (segment.title) baseSegment.title = segment.title;
      if (segment.content) baseSegment.content = segment.content;

      return baseSegment;
    } else {
      // Use a custom segment if no matching type found
      const customSegment = new CustomSegment(params);
      customSegment.type = segmentType;

      // Copy over any existing values
      if (segment.role_taker) customSegment.role_taker = segment.role_taker;
      if (segment.title) customSegment.title = segment.title;
      if (segment.content) customSegment.content = segment.content;

      return customSegment;
    }
  });
}

export default function EditMeetingPage() {
  const params = useParams();
  const router = useRouter();
  const meetingId = params.id as string;

  // Fetch the meeting data
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
        <div className='bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden'>
          <MeetingForm
            initFormData={convertedMeeting}
            mode='edit'
            meetingId={meetingId}
          />
        </div>
      </div>
    </div>
  );
}
