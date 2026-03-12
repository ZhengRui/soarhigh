'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Play,
  Square,
  Bell,
  Save,
  X,
  ChevronLeft,
  ChevronRight,
  Trash2,
  AlertTriangle,
} from 'lucide-react';
import { TimingIF, SegmentIF } from '@/interfaces';
import {
  dotColors,
  getCardTimes,
  getCountdownZone,
  formatDuration,
  formatRelativeDuration,
  formatTime,
  getTimingsForSegment,
  timerTextColors,
  TABLE_TOPICS_SEGMENT_TYPE,
  getCachedTimingTooltip,
  parseDurationToMinutes,
} from '@/utils/timing';
import {
  CachedTimingsState,
  getUnsavedCount,
  hasUnsavedTiming,
  clearCachedTimings,
} from '@/utils/timingStorage';
import { createTimingBatchAll } from '@/utils/timing';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { SegmentCard } from './SegmentCard';
import { TableTopicsTimer } from './TableTopicsTimer';
import { TimingConfirmDialog } from './TimingConfirmDialog';
import { CardSignals } from './TimerComponents';
import { RunningTimerState } from './TimerTab';

interface TimingSubtabProps {
  meetingId: string;
  segments: SegmentIF[];
  timings: TimingIF[];
  // Lifted state from TimerTab
  runningTimer: RunningTimerState | null;
  setRunningTimer: (state: RunningTimerState | null) => void;
  stopRunningTimer: () => void;
  selectedSegmentId: string | null;
  setSelectedSegmentId: (id: string | null) => void;
  // Cached timings from localStorage (managed by TimerTab)
  cachedTimings: CachedTimingsState;
  updateCache: (cache: CachedTimingsState) => void;
  timingWindowStatus: 'can-time' | 'too-early' | 'too-late';
  timingWindowMessage: string;
}

// Check if segment is Table Topic Session (the only special segment type)
function isTableTopicsSegment(segment: SegmentIF): boolean {
  return segment.type === TABLE_TOPICS_SEGMENT_TYPE;
}

type TimingConfirmAction =
  | { type: 'retime' }
  | { type: 'discard-all' }
  | { type: 'discard-entry'; segmentId: string; entryIndex: number }
  | { type: 'save-all' };

interface TimingConfirmState {
  visible: boolean;
  title: string;
  message: string;
  confirmText: string;
  confirmDanger: boolean;
  action: TimingConfirmAction | null;
}

const emptyConfirmDialog: TimingConfirmState = {
  visible: false,
  title: '',
  message: '',
  confirmText: 'Confirm',
  confirmDanger: false,
  action: null,
};

export function TimingSubtab({
  meetingId,
  segments,
  timings,
  runningTimer,
  setRunningTimer,
  stopRunningTimer,
  selectedSegmentId,
  setSelectedSegmentId,
  cachedTimings,
  updateCache,
  timingWindowStatus,
  timingWindowMessage,
}: TimingSubtabProps) {
  const [elapsed, setElapsed] = useState(0);
  const [confirmDialog, setConfirmDialog] =
    useState<TimingConfirmState>(emptyConfirmDialog);
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
    if (timingWindowStatus !== 'can-time') {
      return;
    }

    // Check if there's existing timing OR unsaved cached timing
    if (hasTiming || hasCachedTiming) {
      setConfirmDialog({
        visible: true,
        title: 'Re-time this segment?',
        message:
          'This segment already has a timing record. Starting will cache a new timing locally. Click "Save All" to sync to server.',
        confirmText: 'Start Anyway',
        confirmDanger: false,
        action: { type: 'retime' },
      });
    } else {
      startTimer();
    }
  }, [hasCachedTiming, hasTiming, startTimer, timingWindowStatus]);

  // Navigation handlers
  const currentSegmentIndex = segments.findIndex(
    (s) => s.id === selectedSegmentId
  );
  const canGoPrev = currentSegmentIndex > 0;
  const canGoNext = currentSegmentIndex < segments.length - 1;

  const handleGoPrev = useCallback(() => {
    if (canGoPrev) {
      setSelectedSegmentId(segments[currentSegmentIndex - 1].id);
    }
  }, [canGoPrev, segments, currentSegmentIndex, setSelectedSegmentId]);

  const handleGoNext = useCallback(() => {
    if (canGoNext) {
      setSelectedSegmentId(segments[currentSegmentIndex + 1].id);
    }
  }, [canGoNext, segments, currentSegmentIndex, setSelectedSegmentId]);

  // Handle Save All - batch save all cached timings
  const performSaveAll = useCallback(async () => {
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

  // Handle Discard All - clear all cached timings
  const performDiscardAll = useCallback(() => {
    clearCachedTimings(meetingId);
    updateCache({});
  }, [meetingId, updateCache]);

  // Handle removing a single cached entry
  const removeCachedEntry = useCallback(
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

  const closeConfirmDialog = useCallback(() => {
    setConfirmDialog(emptyConfirmDialog);
  }, []);

  const handleConfirmDialog = useCallback(() => {
    const action = confirmDialog.action;
    setConfirmDialog(emptyConfirmDialog);

    if (!action) {
      return;
    }

    switch (action.type) {
      case 'retime':
        startTimer();
        break;
      case 'discard-all':
        performDiscardAll();
        break;
      case 'discard-entry':
        removeCachedEntry(action.segmentId, action.entryIndex);
        break;
      case 'save-all':
        void performSaveAll();
        break;
      default:
        break;
    }
  }, [
    confirmDialog.action,
    performDiscardAll,
    performSaveAll,
    removeCachedEntry,
    startTimer,
  ]);

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
      {timingWindowMessage && (
        <div className='bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3'>
          <AlertTriangle className='w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0' />
          <p className='text-sm text-amber-800'>{timingWindowMessage}</p>
        </div>
      )}

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
            const isSegmentTableTopics = isTableTopicsSegment(segment);
            const cachedEntries = cachedTimings[segment.id]?.entries || [];
            const speakerEntries = isSegmentTableTopics
              ? segTimings.length > 0
                ? segTimings.map((timing) => ({
                    id: timing.id,
                    name: timing.name,
                    dotColor: timing.dot_color,
                    actualDurationSeconds: timing.actual_duration_seconds,
                    plannedDurationMinutes: timing.planned_duration_minutes,
                    actualStartTime: formatTime(timing.actual_start_time),
                    actualEndTime: formatTime(timing.actual_end_time),
                  }))
                : cachedEntries.map((entry, entryIndex) => ({
                    id: `${segment.id}-cached-${entryIndex}`,
                    name: entry.name,
                    dotColor: entry.dotColor,
                    actualDurationSeconds: Math.floor(
                      (entry.endedAt - entry.startedAt) / 1000
                    ),
                    plannedDurationMinutes: entry.plannedDurationMinutes,
                    isCached: true,
                  }))
              : undefined;
            const cachedTiming =
              !isSegmentTableTopics && cachedEntries[0]
                ? {
                    dotColor: cachedEntries[0].dotColor,
                    actualDurationSeconds: Math.floor(
                      (cachedEntries[0].endedAt - cachedEntries[0].startedAt) /
                        1000
                    ),
                  }
                : null;

            return (
              <SegmentCard
                key={segment.id}
                segment={segment}
                isSelected={segment.id === selectedSegmentId}
                timing={segmentLatestTiming}
                speakerEntries={speakerEntries}
                cachedTiming={cachedTiming}
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
          runningTimer={runningTimer}
          setRunningTimer={setRunningTimer}
          stopRunningTimer={stopRunningTimer}
          cachedTimings={cachedTimings}
          updateCache={updateCache}
          timingWindowStatus={timingWindowStatus}
          canGoPrev={canGoPrev}
          canGoNext={canGoNext}
          onGoPrev={handleGoPrev}
          onGoNext={handleGoNext}
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

          {/* Control Buttons */}
          <div className='flex items-center justify-center gap-3 mt-2'>
            {/* Prev Button */}
            <button
              onClick={handleGoPrev}
              disabled={!canGoPrev}
              className='flex items-center justify-center w-10 h-10 rounded-full text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'
              title='Previous segment'
            >
              <ChevronLeft className='w-5 h-5' />
            </button>

            {/* Start/Stop Button */}
            {!isThisSegmentRunning ? (
              <button
                onClick={handleStartClick}
                disabled={
                  isAnyTimerRunning || timingWindowStatus !== 'can-time'
                }
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
              >
                <Play className='w-4 h-4' />
                Start
              </button>
            ) : (
              <button
                onClick={stopRunningTimer}
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gray-800 hover:bg-gray-900 transition-colors'
              >
                <Square className='w-4 h-4' />
                Stop
              </button>
            )}

            {/* Next Button */}
            <button
              onClick={handleGoNext}
              disabled={!canGoNext}
              className='flex items-center justify-center w-10 h-10 rounded-full text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'
              title='Next segment'
            >
              <ChevronRight className='w-5 h-5' />
            </button>
          </div>
        </div>
      )}

      {/* Unsaved Changes List */}
      <div className='bg-white border border-gray-200 rounded-lg p-4'>
        <div className='flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-2 mb-3'>
          <h4 className='text-xs font-medium text-gray-500'>
            Unsaved Changes ({unsavedEntries.length})
          </h4>
          <div className='flex items-center gap-2'>
            <button
              onClick={() =>
                setConfirmDialog({
                  visible: true,
                  title: 'Discard all unsaved changes?',
                  message: `This will discard ${unsavedCount} locally cached timing${
                    unsavedCount > 1 ? 's' : ''
                  } that haven't been synced to server. To delete saved records, use the Report tab.`,
                  confirmText: 'Discard All',
                  confirmDanger: true,
                  action: { type: 'discard-all' },
                })
              }
              disabled={unsavedCount === 0}
              className='flex-1 sm:flex-none flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
            >
              <Trash2 className='w-3.5 h-3.5' />
              Discard All
            </button>
            <button
              onClick={() =>
                setConfirmDialog({
                  visible: true,
                  title: 'Save all unsaved timings?',
                  message: `This will push ${unsavedCount} locally cached timing${
                    unsavedCount > 1 ? 's' : ''
                  } to the server and remove ${
                    unsavedCount > 1 ? 'them' : 'it'
                  } from local cache. Suggest to save after timing all important segments, but you can still save now.`,
                  confirmText: 'Save All',
                  confirmDanger: false,
                  action: { type: 'save-all' },
                })
              }
              disabled={isSavingAll || isAnyTimerRunning || unsavedCount === 0}
              className={`flex-1 sm:flex-none flex items-center justify-center gap-1.5 py-1.5 px-4 rounded-md text-xs font-medium text-white transition-colors ${
                unsavedCount > 0
                  ? 'bg-amber-600 hover:bg-amber-700'
                  : 'bg-gray-400 cursor-not-allowed'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              <Save className='w-3.5 h-3.5' />
              {isSavingAll ? 'Saving...' : 'Save All'}
            </button>
          </div>
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
                  title={getCachedTimingTooltip(entry)}
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
                        setConfirmDialog({
                          visible: true,
                          title: 'Discard unsaved timing?',
                          message: `This will discard the locally cached timing for ${
                            name ? `"${name}"` : 'this timing'
                          } that hasn't been synced to server.`,
                          confirmText: 'Discard',
                          confirmDanger: true,
                          action: {
                            type: 'discard-entry',
                            segmentId: segment.id,
                            entryIndex,
                          },
                        })
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

      <TimingConfirmDialog
        visible={confirmDialog.visible}
        title={confirmDialog.title}
        message={confirmDialog.message}
        confirmText={confirmDialog.confirmText}
        confirmDanger={confirmDialog.confirmDanger}
        confirmDisabled={
          isSavingAll && confirmDialog.action?.type === 'save-all'
        }
        cancelDisabled={
          isSavingAll && confirmDialog.action?.type === 'save-all'
        }
        onCancel={closeConfirmDialog}
        onConfirm={handleConfirmDialog}
      />
    </div>
  );
}
