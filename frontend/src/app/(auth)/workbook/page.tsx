'use client';

import React, { useState, useEffect } from 'react';
import AgendaWorkbook from '@/components/AgendaWorkbook';
import { MeetingIF } from '@/interfaces';
import { useMeetings } from '@/hooks/useMeetings';

const WorkbookPage = () => {
  const [selectedMeetingId, setSelectedMeetingId] = useState<string>('');
  const [currentMeeting, setCurrentMeeting] = useState<MeetingIF | null>(null);

  // Fetch published meetings using the useMeetings hook
  const { data: paginatedMeetings, isPending: isLoadingMeetings } = useMeetings(
    {
      page: 1,
      pageSize: 5,
      status: 'published',
    }
  );

  // Extract meetings from paginated result
  const meetings = paginatedMeetings?.items || [];

  // When meetings load, select the first one by default
  useEffect(() => {
    if (meetings && meetings.length > 0 && !selectedMeetingId) {
      setSelectedMeetingId(meetings[0].id || '');
    }
  }, [meetings, selectedMeetingId]);

  // When selected meeting changes, update current meeting
  useEffect(() => {
    if (selectedMeetingId && meetings) {
      const meeting = meetings.find((m) => m.id === selectedMeetingId);
      if (meeting) {
        setCurrentMeeting(meeting);
      }
    }
  }, [selectedMeetingId, meetings]);

  // Handle meeting selection change
  const handleMeetingChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedMeetingId(e.target.value);
  };

  if (isLoadingMeetings) {
    return (
      <div className='container py-8'>
        <div className='flex justify-center items-center h-64'>
          <div className='animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500'></div>
        </div>
      </div>
    );
  }

  if (!meetings || meetings.length === 0) {
    return (
      <div className='container py-8'>
        <div className='text-center p-8'>
          <h2 className='text-xl font-semibold mb-4'>No Published Meetings</h2>
          <p className='text-gray-600'>
            There are no published meetings available to generate a workbook.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className='container py-8'>
      <div className='mb-8'>
        <label
          htmlFor='meeting-select'
          className='block text-sm font-medium text-gray-700 mb-2'
        >
          Select Meeting
        </label>
        <select
          id='meeting-select'
          value={selectedMeetingId}
          onChange={handleMeetingChange}
          className='mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md'
        >
          {meetings.map((meeting) => (
            <option key={meeting.id} value={meeting.id || ''}>
              {meeting.no} - {meeting.theme} ({meeting.date})
            </option>
          ))}
        </select>
      </div>

      {currentMeeting && <AgendaWorkbook meeting={currentMeeting} />}
    </div>
  );
};

export default WorkbookPage;
