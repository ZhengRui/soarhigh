'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Clock, FileText, ArrowUpDown, Clock3 } from 'lucide-react';
import toast from 'react-hot-toast';
import { useSegmentTimings } from '@/hooks/useSegmentTimings';
import { SegmentIF, TimingIF } from '@/interfaces';
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
import {
  determineTimingWindowStatus,
  getTimingDotColor,
  parseDurationToMinutes,
  TABLE_TOPICS_SEGMENT_TYPE,
  TABLE_TOPICS_SPEAKER_MINUTES,
  TimingWindowState,
} from '@/utils/timing';

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
  meetingDate: string;
  meetingStartTime: string;
  meetingEndTime: string;
  segments: SegmentIF[];
  onTimingsUpdated?: (canControl: boolean, timings: TimingIF[]) => void;
}

export function TimerTab({
  meetingId,
  meetingDate,
  meetingStartTime,
  meetingEndTime,
  segments,
  onTimingsUpdated,
}: TimerTabProps) {
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
  const [timingWindow, setTimingWindow] = useState<TimingWindowState>(() =>
    determineTimingWindowStatus(meetingDate, meetingStartTime, meetingEndTime)
  );

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

  useEffect(() => {
    const syncTimingWindow = () => {
      setTimingWindow(
        determineTimingWindowStatus(
          meetingDate,
          meetingStartTime,
          meetingEndTime
        )
      );
    };

    syncTimingWindow();
    const intervalId = window.setInterval(syncTimingWindow, 30000);
    return () => window.clearInterval(intervalId);
  }, [meetingDate, meetingEndTime, meetingStartTime]);

  // Persist to localStorage whenever cache changes
  const updateCache = useCallback(
    (newCache: CachedTimingsState) => {
      setCachedTimings(newCache);
      saveCachedTimings(meetingId, newCache);
    },
    [meetingId]
  );

  const stopRunningTimer = useCallback(() => {
    if (!runningTimer?.startedAt || !runningTimer.segmentId) {
      return;
    }

    const timedSegment = segments.find(
      (segment) => segment.id === runningTimer.segmentId
    );
    if (!timedSegment) {
      setRunningTimer(null);
      return;
    }

    const isTableTopics = timedSegment.type === TABLE_TOPICS_SEGMENT_TYPE;
    const plannedMinutes = isTableTopics
      ? TABLE_TOPICS_SPEAKER_MINUTES
      : parseDurationToMinutes(timedSegment.duration);
    const endedAt = Date.now();
    const entry = {
      name:
        runningTimer.speakerName.trim() ||
        timedSegment.role_taker?.name ||
        null,
      plannedDurationMinutes: plannedMinutes,
      startedAt: runningTimer.startedAt,
      endedAt,
      dotColor: getTimingDotColor(
        plannedMinutes,
        Math.floor((endedAt - runningTimer.startedAt) / 1000)
      ),
    };
    const existingEntries = cachedTimings[timedSegment.id]?.entries || [];
    const nextEntries = isTableTopics ? [...existingEntries, entry] : [entry];

    updateCache({
      ...cachedTimings,
      [timedSegment.id]: {
        segmentId: timedSegment.id,
        segmentType: timedSegment.type,
        entries: nextEntries,
      },
    });
    setRunningTimer(null);
  }, [cachedTimings, runningTimer, segments, updateCache]);

  useEffect(() => {
    if (!runningTimer?.isRunning || timingWindow.status !== 'too-late') {
      return;
    }

    stopRunningTimer();
    toast.error('Timing window closed');
  }, [runningTimer?.isRunning, stopRunningTimer, timingWindow.status]);

  useEffect(() => {
    if (
      !runningTimer?.isRunning ||
      typeof navigator === 'undefined' ||
      !('wakeLock' in navigator)
    ) {
      return;
    }

    type WakeLockHandle = {
      released?: boolean;
      release: () => Promise<void>;
    };

    const wakeLockApi = (
      navigator as Navigator & {
        wakeLock?: { request: (type: 'screen') => Promise<WakeLockHandle> };
      }
    ).wakeLock;
    let wakeLock: WakeLockHandle | null = null;

    const requestWakeLock = async () => {
      if (!wakeLockApi) {
        return;
      }

      try {
        wakeLock = await wakeLockApi.request('screen');
      } catch (error) {
        console.error('Failed to acquire wake lock:', error);
      }
    };

    const handleVisibilityChange = () => {
      if (
        document.visibilityState === 'visible' &&
        runningTimer.isRunning &&
        (!wakeLock || wakeLock.released)
      ) {
        void requestWakeLock();
      }
    };

    void requestWakeLock();
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (wakeLock) {
        void wakeLock.release().catch(() => undefined);
      }
    };
  }, [runningTimer?.isRunning]);

  const canControl = data?.can_control ?? false;
  const timings = data?.timings ?? [];

  useEffect(() => {
    if (!data || !onTimingsUpdated) {
      return;
    }

    onTimingsUpdated(data.can_control, data.timings);
  }, [data, onTimingsUpdated]);

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
          stopRunningTimer={stopRunningTimer}
          selectedSegmentId={selectedSegmentId}
          setSelectedSegmentId={setSelectedSegmentId}
          cachedTimings={cachedTimings}
          updateCache={updateCache}
          timingWindowStatus={timingWindow.status}
          timingWindowMessage={timingWindow.message}
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
