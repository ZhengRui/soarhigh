'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAtom } from 'jotai';
import { createPortal } from 'react-dom';
import { Play, Square, Bell } from 'lucide-react';
import { TimingIF, TimingCreateIF, SegmentIF } from '@/interfaces';
import {
  dotColors,
  getCardTimes,
  getCountdownZone,
  formatDuration,
  formatTime,
  getTimingsForSegment,
  timerTextColors,
  TABLE_TOPICS_SEGMENT_TYPE,
} from '@/utils/timing';
import { useCreateTiming } from '@/hooks/useSegmentTimings';
import { runningTimerAtom, selectedSegmentIdAtom } from '@/atoms/timerAtoms';
import toast from 'react-hot-toast';
import { SegmentCard } from './SegmentCard';
import { TableTopicsTimer } from './TableTopicsTimer';
import { CardSignals } from './TimerComponents';

interface TimingSubtabProps {
  meetingId: string;
  segments: SegmentIF[];
  timings: TimingIF[];
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
}: TimingSubtabProps) {
  const [elapsed, setElapsed] = useState(0);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Use Jotai atoms for persistent state
  const [runningTimer, setRunningTimer] = useAtom(runningTimerAtom);
  const [selectedSegmentId, setSelectedSegmentId] = useAtom(
    selectedSegmentIdAtom
  );

  const createTimingMutation = useCreateTiming(meetingId);

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

  // Update elapsed time when this segment's timer is running
  useEffect(() => {
    if (!isThisSegmentRunning || !runningTimer?.startedAt) {
      // Don't reset elapsed if we're saving (keep it frozen)
      return;
    }

    // Capture startedAt to satisfy TypeScript in the interval callback
    const startedAt = runningTimer.startedAt;

    // Immediately calculate elapsed on mount
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
      speakerName: '', // Not used for regular segments
    });
    setElapsed(0);
  }, [selectedSegmentId, setRunningTimer]);

  const handleStartClick = useCallback(() => {
    if (hasTiming) {
      setShowConfirmDialog(true);
    } else {
      startTimer();
    }
  }, [hasTiming, startTimer]);

  const handleConfirmStart = useCallback(() => {
    setShowConfirmDialog(false);
    startTimer();
  }, [startTimer]);

  const handleStop = useCallback(async () => {
    if (!runningTimer?.startedAt || !selectedSegment) return;

    // Capture values before clearing state
    const startedAt = runningTimer.startedAt;
    const endTime = Date.now();

    // Stop the timer immediately (so counter stops updating) but keep elapsed frozen
    setRunningTimer(null);
    setIsSaving(true);

    const timingData: TimingCreateIF = {
      segment_id: selectedSegment.id,
      name: selectedSegment.role_taker?.name || null,
      planned_duration_minutes: plannedMinutes,
      actual_start_time: new Date(startedAt).toISOString(),
      actual_end_time: new Date(endTime).toISOString(),
    };

    try {
      await createTimingMutation.mutateAsync(timingData);
      toast.success('Timing saved!');
      setElapsed(0); // Only reset after successful save
    } catch (error) {
      toast.error('Failed to save timing');
      console.error('Failed to save timing:', error);
    } finally {
      setIsSaving(false);
    }
  }, [
    runningTimer,
    selectedSegment,
    plannedMinutes,
    createTimingMutation,
    setRunningTimer,
  ]);

  // Get current zone color
  const zone = getCountdownZone(plannedMinutes, elapsed);
  const cards = getCardTimes(plannedMinutes);
  const remaining = Math.max(0, cards.red - elapsed);

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
            const latestTiming =
              segTimings.length > 0 ? segTimings[segTimings.length - 1] : null;

            return (
              <SegmentCard
                key={segment.id}
                segment={segment}
                isSelected={segment.id === selectedSegmentId}
                timing={latestTiming}
                onClick={() => setSelectedSegmentId(segment.id)}
                disabled={false}
                isRunning={segment.id === runningSegmentId && isAnyTimerRunning}
              />
            );
          })}
        </div>
      </div>

      {/* Table Topics Timer - special UI for multiple speakers */}
      {selectedSegment && isTableTopics && (
        <TableTopicsTimer
          meetingId={meetingId}
          segment={selectedSegment}
          timings={getTimingsForSegment(timings, selectedSegment.id)}
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
                {latestTiming && !isThisSegmentRunning && (
                  <>
                    <span className='font-mono tabular-nums'>
                      {formatTime(latestTiming.actual_start_time)} -{' '}
                      {formatTime(latestTiming.actual_end_time)}
                    </span>
                    <span className='flex items-center gap-1'>
                      <span className='font-mono tabular-nums'>
                        Used:{' '}
                        {formatDuration(latestTiming.actual_duration_seconds)}
                      </span>
                      <span className='inline-flex items-center justify-center w-3 h-3'>
                        {latestTiming.dot_color === 'bell' ? (
                          <Bell className='w-3 h-3 text-red-600 fill-red-600' />
                        ) : (
                          <span
                            className={`inline-block w-2 h-2 rounded-full ${dotColors[latestTiming.dot_color]}`}
                          ></span>
                        )}
                      </span>
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
                  isThisSegmentRunning || isSaving
                    ? timerTextColors[zone]
                    : 'text-gray-300'
                }`}
              >
                {formatDuration(isThisSegmentRunning || isSaving ? elapsed : 0)}
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
            {isSaving ? (
              <button
                disabled
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gray-600 opacity-50 cursor-not-allowed'
              >
                Saving...
              </button>
            ) : !isThisSegmentRunning ? (
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
