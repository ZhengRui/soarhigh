'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Play, Square, Bell, Save, X } from 'lucide-react';
import { TimingIF, SegmentIF } from '@/interfaces';
import {
  dotColors,
  getCardTimes,
  getCountdownZone,
  formatDuration,
  formatRelativeDuration,
  formatTime,
  getTimingsForSegment,
  getTimingDotColor,
  timerTextColors,
  TABLE_TOPICS_SEGMENT_TYPE,
} from '@/utils/timing';
import {
  CachedTimingsState,
  CachedTimingEntry,
  getUnsavedCount,
  hasUnsavedTiming,
  clearCachedTimings,
} from '@/utils/timingStorage';
import { createTimingBatchAll } from '@/utils/timing';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { SegmentCard } from './SegmentCard';
import { TableTopicsTimer } from './TableTopicsTimer';
import { CardSignals } from './TimerComponents';
import { RunningTimerState } from './TimerTab';

interface TimingSubtabProps {
  meetingId: string;
  segments: SegmentIF[];
  timings: TimingIF[];
  // Lifted state from TimerTab
  runningTimer: RunningTimerState | null;
  setRunningTimer: (state: RunningTimerState | null) => void;
  selectedSegmentId: string | null;
  setSelectedSegmentId: (id: string | null) => void;
  // Cached timings from localStorage (managed by TimerTab)
  cachedTimings: CachedTimingsState;
  updateCache: (cache: CachedTimingsState) => void;
}

// Parse duration string like "5", "5min", or "1h30min" to minutes
function parseDurationToMinutes(duration: string): number {
  // Handle plain number (just digits)
  if (/^\d+$/.test(duration.trim())) {
    return parseInt(duration.trim(), 10);
  }

  const hourMatch = duration.match(/(\d+)h/);
  const minMatch = duration.match(/(\d+)min/);

  const hours = hourMatch ? parseInt(hourMatch[1], 10) : 0;
  const mins = minMatch ? parseInt(minMatch[1], 10) : 0;

  return hours * 60 + mins;
}

// Check if segment is Table Topic Session (the only special segment type)
function isTableTopicsSegment(segment: SegmentIF): boolean {
  return segment.type === TABLE_TOPICS_SEGMENT_TYPE;
}

export function TimingSubtab({
  meetingId,
  segments,
  timings,
  runningTimer,
  setRunningTimer,
  selectedSegmentId,
  setSelectedSegmentId,
  cachedTimings,
  updateCache,
}: TimingSubtabProps) {
  const [elapsed, setElapsed] = useState(0);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [isSavingAll, setIsSavingAll] = useState(false);
  const [showRelative, setShowRelative] = useState(false);

  const queryClient = useQueryClient();

  // Find selected segment
  const selectedSegment = segments.find((s) => s.id === selectedSegmentId);
  const plannedMinutes = selectedSegment
    ? parseDurationToMinutes(selectedSegment.duration)
    : 0;

  // Check if this segment's timer is running (for regular segments, not Table Topics)
  const isThisSegmentRunning =
    runningTimer?.segmentId === selectedSegmentId && runningTimer.isRunning;

  // Check if any timer is running (could be on a different segment)
  const isAnyTimerRunning = runningTimer?.isRunning ?? false;
  const runningSegmentId = runningTimer?.segmentId ?? null;

  // Get timings for selected segment
  const segmentTimings = selectedSegmentId
    ? getTimingsForSegment(timings, selectedSegmentId)
    : [];
  const hasTiming = segmentTimings.length > 0;
  const latestTiming = hasTiming
    ? segmentTimings[segmentTimings.length - 1]
    : null;

  // Check for unsaved cached timing
  const hasCachedTiming =
    selectedSegmentId && hasUnsavedTiming(cachedTimings, selectedSegmentId);
  const cachedEntry = hasCachedTiming
    ? cachedTimings[selectedSegmentId]?.entries[0]
    : null;

  // Count total unsaved segments
  const unsavedCount = getUnsavedCount(cachedTimings);

  // Update elapsed time when this segment's timer is running
  useEffect(() => {
    if (!isThisSegmentRunning || !runningTimer?.startedAt) {
      return;
    }

    const startedAt = runningTimer.startedAt;
    setElapsed(Math.floor((Date.now() - startedAt) / 1000));

    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 100);

    return () => clearInterval(interval);
  }, [isThisSegmentRunning, runningTimer?.startedAt]);

  // Auto-select first segment if none selected
  useEffect(() => {
    if (!selectedSegmentId && segments.length > 0) {
      setSelectedSegmentId(segments[0].id);
    }
  }, [segments, selectedSegmentId, setSelectedSegmentId]);

  // Check if selected segment is Table Topics
  const isTableTopics =
    selectedSegment && isTableTopicsSegment(selectedSegment);

  const startTimer = useCallback(() => {
    if (!selectedSegmentId) return;
    setRunningTimer({
      segmentId: selectedSegmentId,
      isRunning: true,
      startedAt: Date.now(),
      speakerName: '',
    });
    setElapsed(0);
  }, [selectedSegmentId, setRunningTimer]);

  const handleStartClick = useCallback(() => {
    // Check if there's existing timing OR unsaved cached timing
    if (hasTiming || hasCachedTiming) {
      setShowConfirmDialog(true);
    } else {
      startTimer();
    }
  }, [hasTiming, hasCachedTiming, startTimer]);

  const handleConfirmStart = useCallback(() => {
    setShowConfirmDialog(false);
    startTimer();
  }, [startTimer]);

  // Handle stop - cache locally instead of saving immediately
  const handleStop = useCallback(() => {
    if (!runningTimer?.startedAt || !selectedSegment) return;

    const startedAt = runningTimer.startedAt;
    const endedAt = Date.now();
    const durationSeconds = Math.floor((endedAt - startedAt) / 1000);
    const dotColor = getTimingDotColor(plannedMinutes, durationSeconds);

    const entry: CachedTimingEntry = {
      name: selectedSegment.role_taker?.name || null,
      plannedDurationMinutes: plannedMinutes,
      startedAt,
      endedAt,
      dotColor,
    };

    // Cache the timing (overwrites any existing cache for this segment)
    updateCache({
      ...cachedTimings,
      [selectedSegment.id]: {
        segmentId: selectedSegment.id,
        segmentType: selectedSegment.type,
        entries: [entry],
      },
    });

    setRunningTimer(null);
    setElapsed(0);
  }, [
    runningTimer,
    selectedSegment,
    plannedMinutes,
    cachedTimings,
    updateCache,
    setRunningTimer,
  ]);

  // Handle Save All - batch save all cached timings
  const handleSaveAll = useCallback(async () => {
    if (unsavedCount === 0) return;

    setIsSavingAll(true);

    const segmentsData = Object.values(cachedTimings).map((seg) => ({
      segment_id: seg.segmentId,
      timings: seg.entries.map((e) => ({
        name: e.name,
        planned_duration_minutes: e.plannedDurationMinutes,
        actual_start_time: new Date(e.startedAt).toISOString(),
        actual_end_time: new Date(e.endedAt).toISOString(),
      })),
    }));

    try {
      await createTimingBatchAll(meetingId, { segments: segmentsData });
      clearCachedTimings(meetingId);
      updateCache({});
      queryClient.invalidateQueries({ queryKey: ['timings', meetingId] });
      toast.success(`Saved ${unsavedCount} timing(s)`);
    } catch (error) {
      toast.error('Failed to save timings');
      console.error('Failed to save timings:', error);
    } finally {
      setIsSavingAll(false);
    }
  }, [cachedTimings, unsavedCount, meetingId, updateCache, queryClient]);

  // Handle removing a single cached entry
  const handleRemoveCachedEntry = useCallback(
    (segmentId: string, entryIndex: number) => {
      const segment = cachedTimings[segmentId];
      if (!segment) return;

      const newEntries = segment.entries.filter((_, i) => i !== entryIndex);
      if (newEntries.length === 0) {
        // Remove segment from cache if no entries left
        const { [segmentId]: _removed, ...rest } = cachedTimings;
        void _removed;
        updateCache(rest);
      } else {
        updateCache({
          ...cachedTimings,
          [segmentId]: { ...segment, entries: newEntries },
        });
      }
    },
    [cachedTimings, updateCache]
  );

  // Build flat list of unsaved entries in segment order
  const unsavedEntries = segments.flatMap((segment) => {
    const cached = cachedTimings[segment.id];
    if (!cached) return [];
    return cached.entries.map((entry, entryIndex) => ({
      segment,
      entry,
      entryIndex,
    }));
  });

  // Get current zone color
  const zone = getCountdownZone(plannedMinutes, elapsed);
  const cards = getCardTimes(plannedMinutes);
  const remaining = Math.max(0, cards.red - elapsed);

  // Display timing - prefer cached over saved
  const displayTiming = cachedEntry
    ? {
        actual_start_time: new Date(cachedEntry.startedAt).toISOString(),
        actual_end_time: new Date(cachedEntry.endedAt).toISOString(),
        actual_duration_seconds: Math.floor(
          (cachedEntry.endedAt - cachedEntry.startedAt) / 1000
        ),
        dot_color: cachedEntry.dotColor,
      }
    : latestTiming;

  return (
    <div className='space-y-4'>
      {/* Segment Cards - Horizontal Scrollable (hide scrollbar) */}
      <div
        className='overflow-x-auto pb-2 scrollbar-hide'
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        <style jsx>{`
          div::-webkit-scrollbar {
            display: none;
          }
        `}</style>
        <div className='flex gap-2 min-w-max'>
          {segments.map((segment) => {
            const segTimings = getTimingsForSegment(timings, segment.id);
            const segmentLatestTiming =
              segTimings.length > 0 ? segTimings[segTimings.length - 1] : null;
            const isCached = hasUnsavedTiming(cachedTimings, segment.id);

            return (
              <SegmentCard
                key={segment.id}
                segment={segment}
                isSelected={segment.id === selectedSegmentId}
                timing={segmentLatestTiming}
                onClick={() => setSelectedSegmentId(segment.id)}
                disabled={false}
                isRunning={segment.id === runningSegmentId && isAnyTimerRunning}
                isCached={isCached}
              />
            );
          })}
        </div>
      </div>

      {/* Table Topics Timer - special UI for multiple speakers */}
      {selectedSegment && isTableTopics && (
        <TableTopicsTimer
          segment={selectedSegment}
          timings={getTimingsForSegment(timings, selectedSegment.id)}
          runningTimer={runningTimer}
          setRunningTimer={setRunningTimer}
          cachedTimings={cachedTimings}
          updateCache={updateCache}
        />
      )}

      {/* Regular Countdown Area */}
      {selectedSegment && !isTableTopics && (
        <div className='bg-white border border-gray-200 rounded-lg p-5 sm:p-6'>
          {/* Header: Centered stack on mobile, two-column on desktop */}
          <div className='text-center sm:text-left sm:flex sm:items-start sm:justify-between sm:gap-4 mb-4'>
            {/* Left: Segment info */}
            <div className='space-y-1 sm:space-y-0'>
              <h3 className='text-sm font-medium text-gray-900 truncate'>
                {selectedSegment.type}
              </h3>
              <p className='text-xs text-gray-500 h-4 sm:mt-0.5'>
                {selectedSegment.role_taker?.name || ''}
                {selectedSegment.role_taker?.name &&
                  selectedSegment.title &&
                  ' · '}
                {selectedSegment.title || ''}
              </p>
            </div>
            {/* Right: Checkpoints and used duration */}
            <div className='mt-2 sm:mt-0 sm:text-right space-y-1 sm:space-y-0'>
              {/* Card signal times */}
              <CardSignals plannedMinutes={plannedMinutes} />
              {/* Previous timing info - always reserve height */}
              <div className='text-xs text-gray-400 h-8 flex flex-col items-center sm:items-end justify-center sm:mt-1'>
                {displayTiming && !isThisSegmentRunning && (
                  <>
                    <span className='font-mono tabular-nums'>
                      {formatTime(displayTiming.actual_start_time)} -{' '}
                      {formatTime(displayTiming.actual_end_time)}
                    </span>
                    <span className='flex items-center gap-1'>
                      <span className='font-mono tabular-nums'>
                        Used:{' '}
                        {formatDuration(displayTiming.actual_duration_seconds)}
                      </span>
                      <span className='inline-flex items-center justify-center w-3 h-3'>
                        {displayTiming.dot_color === 'bell' ? (
                          <Bell className='w-3 h-3 text-red-600 fill-red-600' />
                        ) : (
                          <span
                            className={`inline-block w-2 h-2 rounded-full ${dotColors[displayTiming.dot_color]}`}
                          ></span>
                        )}
                      </span>
                      {hasCachedTiming && (
                        <span className='text-amber-600 text-[10px]'>
                          (unsaved)
                        </span>
                      )}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Timer Display */}
          <div className='text-center py-6 sm:py-4'>
            <div className='relative inline-flex items-center justify-center'>
              <span
                className={`text-5xl sm:text-6xl font-mono font-bold tracking-tight transition-colors tabular-nums ${
                  isThisSegmentRunning ? timerTextColors[zone] : 'text-gray-300'
                }`}
              >
                {formatDuration(isThisSegmentRunning ? elapsed : 0)}
              </span>
              {/* Bell icon when 30+ seconds over - floated to the right */}
              {isThisSegmentRunning && zone === 'overtime' && (
                <Bell className='absolute -right-10 sm:-right-12 w-8 h-8 sm:w-10 sm:h-10 text-red-600 fill-red-600 animate-pulse' />
              )}
            </div>
            {/* Time hint - always reserve height */}
            <p className='text-xs text-gray-400 mt-2 h-4 tabular-nums'>
              {isThisSegmentRunning &&
                (elapsed >= cards.red
                  ? `${formatDuration(elapsed - cards.red)} over`
                  : `${formatDuration(remaining)} remaining`)}
            </p>
          </div>

          {/* Control Button */}
          <div className='flex justify-center mt-2'>
            {!isThisSegmentRunning ? (
              <button
                onClick={handleStartClick}
                disabled={isAnyTimerRunning}
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
              >
                <Play className='w-4 h-4' />
                Start
              </button>
            ) : (
              <button
                onClick={handleStop}
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gray-800 hover:bg-gray-900 transition-colors'
              >
                <Square className='w-4 h-4' />
                Stop
              </button>
            )}
          </div>
        </div>
      )}

      {/* Unsaved Changes List */}
      <div className='bg-white border border-gray-200 rounded-lg p-4'>
        <div className='flex items-center justify-between mb-3'>
          <h4 className='text-xs font-medium text-gray-500'>
            Unsaved Changes ({unsavedEntries.length})
          </h4>
          <button
            onClick={handleSaveAll}
            disabled={isSavingAll || isAnyTimerRunning || unsavedCount === 0}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-4 rounded-md text-xs font-medium text-white transition-colors ${
              unsavedCount > 0
                ? 'bg-amber-600 hover:bg-amber-700'
                : 'bg-gray-400 cursor-not-allowed'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            <Save className='w-3.5 h-3.5' />
            {isSavingAll ? 'Saving...' : 'Save All'}
          </button>
        </div>
        {unsavedEntries.length === 0 ? (
          <p className='text-xs text-gray-400 text-center py-2'>
            No unsaved changes
          </p>
        ) : (
          <div className='space-y-1.5'>
            {unsavedEntries.map(({ segment, entry, entryIndex }) => {
              const actualSeconds = Math.floor(
                (entry.endedAt - entry.startedAt) / 1000
              );
              const isSegmentTableTopics = isTableTopicsSegment(segment);
              // For Table Topics, name comes from entry; for others from segment.role_taker
              const name = isSegmentTableTopics
                ? entry.name
                : segment.role_taker?.name;
              const segmentType = segment.type;

              return (
                <div
                  key={`${segment.id}-${entryIndex}`}
                  className='flex items-center justify-between py-2 px-3 bg-amber-50 border border-amber-200 rounded-lg'
                >
                  <div className='flex items-center gap-2 min-w-0'>
                    {entry.dotColor === 'bell' ? (
                      <Bell className='w-3 h-3 text-red-600 fill-red-600 flex-shrink-0' />
                    ) : (
                      <span
                        className={`w-2.5 h-2.5 rounded-full ${dotColors[entry.dotColor]} flex-shrink-0`}
                      />
                    )}
                    <span className='text-xs sm:text-sm text-gray-800 truncate'>
                      {name || segmentType || 'Unknown'}
                      {name && segmentType && (
                        <span className='text-[10px] sm:text-xs text-gray-400'>
                          {' '}
                          · {segmentType}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className='flex items-center gap-1.5 flex-shrink-0 ml-2'>
                    <button
                      onClick={() => setShowRelative(!showRelative)}
                      className='flex items-center gap-1.5 hover:opacity-70 transition-opacity'
                    >
                      <span className='text-xs sm:text-sm font-mono text-gray-800 tabular-nums'>
                        {showRelative
                          ? formatRelativeDuration(
                              actualSeconds,
                              entry.plannedDurationMinutes
                            )
                          : formatDuration(actualSeconds)}
                      </span>
                      <span className='text-[10px] sm:text-[11px] text-gray-400'>
                        / {entry.plannedDurationMinutes}m
                      </span>
                    </button>
                    <button
                      onClick={() =>
                        handleRemoveCachedEntry(segment.id, entryIndex)
                      }
                      className='p-1 text-gray-400 hover:text-red-500 transition-colors'
                      title='Remove'
                    >
                      <X className='w-3.5 h-3.5' />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Confirmation Dialog - rendered via portal to escape overflow-hidden ancestors */}
      {showConfirmDialog &&
        typeof window !== 'undefined' &&
        createPortal(
          <div
            className='fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]'
            onClick={() => setShowConfirmDialog(false)}
          >
            <div
              className='bg-white rounded-lg p-6 mx-4 max-w-sm sm:max-w-md shadow-xl'
              onClick={(e) => e.stopPropagation()}
            >
              <h4 className='text-sm sm:text-base font-medium text-gray-900 mb-2'>
                Re-time this segment?
              </h4>
              <p className='text-xs sm:text-sm text-gray-500 mb-4'>
                This segment has already been timed. Starting will create a new
                timing record.
              </p>
              <div className='flex gap-3 justify-end'>
                <button
                  onClick={() => setShowConfirmDialog(false)}
                  className='px-3 py-1.5 text-xs sm:text-sm text-gray-600 hover:text-gray-800 transition-colors'
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmStart}
                  className='px-4 py-1.5 text-xs sm:text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors'
                >
                  Start Anyway
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
