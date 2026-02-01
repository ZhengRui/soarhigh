'use client';

import React, { useState } from 'react';
import { Clock, FileText } from 'lucide-react';
import { useSegmentTimings } from '@/hooks/useSegmentTimings';
import { SegmentIF } from '@/interfaces';
import { TimingSubtab } from './TimingSubtab';
import { TimerReportSubtab } from './TimerReportSubtab';

interface TimerTabProps {
  meetingId: string;
  segments: SegmentIF[];
}

export function TimerTab({ meetingId, segments }: TimerTabProps) {
  const { data, isLoading, isError } = useSegmentTimings(meetingId);
  const [activeSubtab, setActiveSubtab] = useState<'timing' | 'report'>(
    'timing'
  );

  const canControl = data?.can_control ?? false;
  const timings = data?.timings ?? [];

  if (isLoading) {
    return (
      <div className='flex items-center justify-center py-8'>
        <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600'></div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className='text-center text-red-500 py-8'>
        Failed to load timing data. Please try again.
      </div>
    );
  }

  // For non-Timer members, show report content directly without subtabs
  if (!canControl) {
    return <TimerReportSubtab segments={segments} timings={timings} />;
  }

  // For Timer role holder, show subtabs
  return (
    <div>
      {/* Subtab Navigation - compact centered toggle */}
      <div className='flex justify-center mb-4'>
        <div className='inline-flex bg-gray-100 rounded-full p-0.5'>
          <button
            className={`px-3 py-1 text-xs font-medium rounded-full transition-colors flex items-center gap-1.5 ${
              activeSubtab === 'timing'
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveSubtab('timing')}
          >
            <Clock className='w-3 h-3' />
            Timing
          </button>
          <button
            className={`px-3 py-1 text-xs font-medium rounded-full transition-colors flex items-center gap-1.5 ${
              activeSubtab === 'report'
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveSubtab('report')}
          >
            <FileText className='w-3 h-3' />
            Report
          </button>
        </div>
      </div>

      {/* Subtab Content */}
      {activeSubtab === 'timing' && (
        <TimingSubtab
          meetingId={meetingId}
          segments={segments}
          timings={timings}
        />
      )}
      {activeSubtab === 'report' && (
        <TimerReportSubtab segments={segments} timings={timings} />
      )}
    </div>
  );
}
