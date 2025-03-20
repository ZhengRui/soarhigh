'use client';

import { useMeeting } from '@/hooks/useMeeting';
import AgendaWorkbook from '@/components/AgendaWorkbook';
import { Loader2 } from 'lucide-react';
import { useParams } from 'next/navigation';
import { useState, useEffect } from 'react';
import { MeetingIF } from '@/interfaces';

export default function Page() {
  const params = useParams();
  const meeting_id = Array.isArray(params.id) ? params.id[0] : params.id || '';
  const [previewMeeting, setPreviewMeeting] = useState<MeetingIF | null>(null);

  // Always call hooks at the top level, before any conditional returns
  const { data: meeting, isPending: isLoadingMeeting } = useMeeting(
    meeting_id === 'preview' ? '' : meeting_id
  );

  // Check for localStorage data when meeting_id is "preview"
  useEffect(() => {
    if (meeting_id === 'preview') {
      try {
        const storedMeetingData = localStorage.getItem('tempMeetingData');
        if (storedMeetingData) {
          const meetingData = JSON.parse(storedMeetingData);
          setPreviewMeeting(meetingData);
        }
      } catch (error) {
        console.error('Error parsing meeting data from localStorage:', error);
      }
    }
  }, [meeting_id]);

  // If we're in preview mode and have data from localStorage, use that
  if (meeting_id === 'preview' && previewMeeting) {
    return <AgendaWorkbook meeting={previewMeeting} />;
  }

  if (meeting_id === 'preview' && !previewMeeting) {
    return (
      <div className='flex flex-col items-center justify-center min-h-[80vh] p-8'>
        <p className='text-gray-600'>No preview data available</p>
      </div>
    );
  }

  if (isLoadingMeeting) {
    return (
      <div className='flex flex-col items-center justify-center min-h-[80vh] p-8'>
        <Loader2 className='w-8 h-8 text-blue-500 animate-spin mb-4' />
        <p className='text-gray-600'>Loading meeting data...</p>
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className='flex flex-col items-center justify-center min-h-[80vh] p-8'>
        <p className='text-gray-600'>Meeting not found</p>
      </div>
    );
  }

  return <AgendaWorkbook meeting={meeting} />;
}
