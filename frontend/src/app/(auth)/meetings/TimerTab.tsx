'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Clock, FileText, ArrowUpDown, Clock3 } from 'lucide-react';
import { useSegmentTimings } from '@/hooks/useSegmentTimings';
import { SegmentIF } from '@/interfaces';
import { TimingSubtab } from './TimingSubtab';
import { TimerReportSubtab } from './TimerReportSubtab';
import {
  loadCachedTimings,
  saveCachedTimings,
  cleanupExpiredCaches,
  loadRunningTimer,
  saveRunningTimer,
  CachedTimingsState,
} from '@/utils/timingStorage';

export type ReportSortOrder = 'status' | 'chronological';

// Running timer state - lifted from Jotai to parent component
export interface RunningTimerState {
  segmentId: string;
  isRunning: boolean;
  startedAt: number | null;
  speakerName: string; // Used for Table Topics
}

interface TimerTabProps {
  meetingId: string;
  segments: SegmentIF[];
}

export function TimerTab({ meetingId, segments }: TimerTabProps) {
  const { data, isLoading, isError } = useSegmentTimings(meetingId);
  const [activeSubtab, setActiveSubtab] = useState<'timing' | 'report'>(
    'timing'
  );
  const [reportSortOrder, setReportSortOrder] =
    useState<ReportSortOrder>('status');

  // Lifted state (previously Jotai atoms)
  const [runningTimer, setRunningTimer] = useState<RunningTimerState | null>(
    null
  );
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(
    null
  );

  // Cached timings state (loaded from localStorage)
  const [cachedTimings, setCachedTimings] = useState<CachedTimingsState>({});

  // Cleanup expired caches on mount (runs once)
  useEffect(() => {
    cleanupExpiredCaches();
  }, []);

  // Load from localStorage/sessionStorage on mount
  useEffect(() => {
    const cached = loadCachedTimings(meetingId);
    setCachedTimings(cached);

    const savedTimer = loadRunningTimer(meetingId);
    if (savedTimer) {
      setRunningTimer(savedTimer);
    }
  }, [meetingId]);

  // Persist running timer to sessionStorage whenever it changes
  useEffect(() => {
    saveRunningTimer(meetingId, runningTimer);
  }, [meetingId, runningTimer]);

  // Persist to localStorage whenever cache changes
  const updateCache = useCallback(
    (newCache: CachedTimingsState) => {
      setCachedTimings(newCache);
      saveCachedTimings(meetingId, newCache);
    },
    [meetingId]
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
    return (
      <TimerReportSubtab
        meetingId={meetingId}
        segments={segments}
        timings={timings}
        canControl={false}
      />
    );
  }

  // For Timer role holder, show subtabs
  return (
    <div>
      {/* Subtab Navigation */}
      <div className='flex items-center justify-center relative mb-4'>
        {/* Center - Timing/Report toggle */}
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

        {/* Right side - Sort toggle (only in report view) */}
        {activeSubtab === 'report' && (
          <button
            onClick={() =>
              setReportSortOrder((prev) =>
                prev === 'status' ? 'chronological' : 'status'
              )
            }
            className='absolute right-0 flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-full transition-colors'
            title={
              reportSortOrder === 'status'
                ? 'Sorted by status'
                : 'Sorted by time'
            }
          >
            {reportSortOrder === 'status' ? (
              <>
                <ArrowUpDown className='w-3 h-3' />
                <span className='hidden sm:inline'>Status</span>
              </>
            ) : (
              <>
                <Clock3 className='w-3 h-3' />
                <span className='hidden sm:inline'>Time</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* Subtab Content */}
      {activeSubtab === 'timing' && (
        <TimingSubtab
          meetingId={meetingId}
          segments={segments}
          timings={timings}
          runningTimer={runningTimer}
          setRunningTimer={setRunningTimer}
          selectedSegmentId={selectedSegmentId}
          setSelectedSegmentId={setSelectedSegmentId}
          cachedTimings={cachedTimings}
          updateCache={updateCache}
        />
      )}
      {activeSubtab === 'report' && (
        <TimerReportSubtab
          meetingId={meetingId}
          segments={segments}
          timings={timings}
          canControl={canControl}
          sortOrder={reportSortOrder}
        />
      )}
    </div>
  );
}
