'use client';

import React, { useState, useMemo } from 'react';
import { useDashboardStats } from '@/hooks/useDashboard';
import { MemberRoleMatrix } from './components/MemberRoleMatrix';
import { MemberAttendanceChart } from './components/MemberAttendanceChart';
import { MeetingAttendanceChart } from './components/MeetingAttendanceChart';
import {
  transformMemberAttendanceData,
  transformMeetingAttendanceData,
} from './utils/dataTransforms';

// Helper to format date to YYYY-MM-DD (local timezone)
const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Get default date range (past 3 months)
const getDefaultDateRange = () => {
  const endDate = new Date();
  const startDate = new Date();
  startDate.setMonth(startDate.getMonth() - 3);
  return {
    startDate: formatDate(startDate),
    endDate: formatDate(endDate),
  };
};

export default function DashboardPage() {
  const defaultRange = getDefaultDateRange();
  const [startDate, setStartDate] = useState(defaultRange.startDate);
  const [endDate, setEndDate] = useState(defaultRange.endDate);

  const { data, isPending, error } = useDashboardStats({ startDate, endDate });

  // Transform data for charts
  const memberAttendanceData = useMemo(
    () => transformMemberAttendanceData(data?.member_meetings ?? []),
    [data?.member_meetings]
  );

  const meetingAttendanceData = useMemo(
    () => transformMeetingAttendanceData(data?.meeting_attendance ?? []),
    [data?.meeting_attendance]
  );

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-7xl mx-auto'>
        <div className='text-center mb-8'>
          <h1 className='text-3xl font-bold text-gray-900'>Dashboard</h1>
          <p className='mt-2 text-gray-600'>
            Meeting statistics and member participation insights
          </p>
        </div>

        {/* Date Range Picker */}
        <div className='bg-white p-4 rounded-lg shadow-sm mb-8'>
          <div className='flex flex-wrap items-center gap-4'>
            <label className='text-sm font-medium text-gray-700'>
              Date Range:
            </label>
            <div className='flex items-center gap-2'>
              <input
                type='date'
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className='px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500'
              />
              <span className='text-gray-500'>to</span>
              <input
                type='date'
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className='px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500'
              />
            </div>
          </div>
        </div>

        {isPending && (
          <div className='flex flex-col items-center justify-center py-24'>
            <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600'></div>
            <p className='mt-2 text-gray-600'>Loading statistics...</p>
          </div>
        )}

        {error && (
          <div className='bg-red-50 border border-red-200 rounded-lg p-4 mb-8'>
            <p className='text-red-600'>
              Failed to load dashboard data. Please try again.
            </p>
          </div>
        )}

        {data && (
          <div className='space-y-8'>
            {/* Chart 1: Member Attendance */}
            <div className='bg-white p-6 rounded-lg shadow-sm'>
              <h2 className='text-xl font-semibold mb-4 text-gray-900'>
                Member Attendance
              </h2>
              <p className='text-sm text-gray-600 mb-4'>
                Number of meetings attended by each member (tap bar for details,
                drag to pan)
              </p>
              <MemberAttendanceChart data={memberAttendanceData} />
            </div>

            {/* Chart 2: Meeting Attendance */}
            <div className='bg-white p-6 rounded-lg shadow-sm'>
              <h2 className='text-xl font-semibold mb-4 text-gray-900'>
                Attendance per Meeting
              </h2>
              <p className='text-sm text-gray-600 mb-4'>
                Number of members and guests per meeting (tap bar for names,
                drag to pan)
              </p>
              <MeetingAttendanceChart data={meetingAttendanceData} />
            </div>

            {/* Member-Role Matrix */}
            <MemberRoleMatrix memberMeetings={data.member_meetings} />
          </div>
        )}
      </div>
    </div>
  );
}
