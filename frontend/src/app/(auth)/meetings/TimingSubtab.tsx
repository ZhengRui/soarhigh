'use client';

import React, { useState, useEffect, useCallback } from 'react';
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
} from '@/utils/timing';
import { useCreateTiming } from '@/hooks/useSegmentTimings';
import toast from 'react-hot-toast';
import { SegmentCard } from './SegmentCard';

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
  return segment.type === 'Table Topic Session';
}

export function TimingSubtab({
  meetingId,
  segments,
  timings,
}: TimingSubtabProps) {
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(
    null
  );
  const [isRunning, setIsRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const createTimingMutation = useCreateTiming(meetingId);

  // Find selected segment
  const selectedSegment = segments.find((s) => s.id === selectedSegmentId);
  const plannedMinutes = selectedSegment
    ? parseDurationToMinutes(selectedSegment.duration)
    : 0;

  // Get timings for selected segment
  const segmentTimings = selectedSegmentId
    ? getTimingsForSegment(timings, selectedSegmentId)
    : [];
  const hasTiming = segmentTimings.length > 0;
  const latestTiming = hasTiming
    ? segmentTimings[segmentTimings.length - 1]
    : null;

  // Update elapsed time when running
  useEffect(() => {
    if (!isRunning || !startedAt) return;

    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 100);

    return () => clearInterval(interval);
  }, [isRunning, startedAt]);

  // Auto-select first segment if none selected
  useEffect(() => {
    if (!selectedSegmentId && segments.length > 0) {
      setSelectedSegmentId(segments[0].id);
    }
  }, [segments, selectedSegmentId]);

  const handleStartClick = useCallback(() => {
    if (hasTiming) {
      setShowConfirmDialog(true);
    } else {
      setStartedAt(Date.now());
      setIsRunning(true);
      setElapsed(0);
    }
  }, [hasTiming]);

  const handleConfirmStart = useCallback(() => {
    setShowConfirmDialog(false);
    setStartedAt(Date.now());
    setIsRunning(true);
    setElapsed(0);
  }, []);

  const handleStop = useCallback(async () => {
    if (!startedAt || !selectedSegment) return;

    const endTime = Date.now();
    setIsRunning(false);

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
      setStartedAt(null);
      setElapsed(0);
    } catch (error) {
      toast.error('Failed to save timing');
      console.error('Failed to save timing:', error);
    }
  }, [startedAt, selectedSegment, plannedMinutes, createTimingMutation]);

  // Get current zone color
  const zone = getCountdownZone(plannedMinutes, elapsed);
  const cards = getCardTimes(plannedMinutes);
  const remaining = Math.max(0, cards.red - elapsed);

  // Timer text colors based on zone
  const timerTextColor: Record<string, string> = {
    gray: 'text-gray-400',
    green: 'text-green-600',
    yellow: 'text-yellow-600',
    red: 'text-red-600',
    overtime: 'text-red-600',
  };

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
                onClick={() => {
                  if (!isRunning) {
                    setSelectedSegmentId(segment.id);
                  }
                }}
                disabled={isRunning}
              />
            );
          })}
        </div>
      </div>

      {/* Countdown Area */}
      {selectedSegment && (
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
              {/* Card signal times - fixed width for consistency */}
              <div className='flex items-center justify-center sm:justify-end gap-3 text-xs'>
                <span className='text-green-600 font-mono'>
                  <span className='inline-block w-2 h-2 bg-green-500 rounded-full mr-1'></span>
                  <span className='inline-block w-10 text-left'>
                    {formatDuration(cards.green)}
                  </span>
                </span>
                <span className='text-yellow-600 font-mono'>
                  <span className='inline-block w-2 h-2 bg-yellow-500 rounded-full mr-1'></span>
                  <span className='inline-block w-10 text-left'>
                    {formatDuration(cards.yellow)}
                  </span>
                </span>
                <span className='text-red-600 font-mono'>
                  <span className='inline-block w-2 h-2 bg-red-500 rounded-full mr-1'></span>
                  <span className='inline-block w-10 text-left'>
                    {formatDuration(cards.red)}
                  </span>
                </span>
              </div>
              {/* Previous timing info - always reserve height */}
              <div className='text-xs text-gray-400 h-8 flex flex-col items-center sm:items-end justify-center sm:mt-1'>
                {latestTiming && !isRunning && (
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
                  isRunning ? timerTextColor[zone] : 'text-gray-300'
                }`}
              >
                {formatDuration(elapsed)}
              </span>
              {/* Bell icon when 30+ seconds over - floated to the right */}
              {isRunning && zone === 'overtime' && (
                <Bell className='absolute -right-10 sm:-right-12 w-8 h-8 sm:w-10 sm:h-10 text-red-600 fill-red-600 animate-pulse' />
              )}
            </div>
            {/* Time hint - always reserve height */}
            <p className='text-xs text-gray-400 mt-2 h-4 tabular-nums'>
              {isRunning &&
                (elapsed >= cards.red
                  ? `${formatDuration(elapsed - cards.red)} over`
                  : `${formatDuration(remaining)} remaining`)}
            </p>
          </div>

          {/* Control Button */}
          <div className='flex justify-center mt-2'>
            {!isRunning ? (
              <button
                onClick={handleStartClick}
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 transition-colors'
              >
                <Play className='w-4 h-4' />
                Start
              </button>
            ) : (
              <button
                onClick={handleStop}
                disabled={createTimingMutation.isPending}
                className='flex items-center justify-center gap-2 py-2 px-6 rounded-md text-sm font-medium text-white bg-gray-800 hover:bg-gray-900 transition-colors disabled:opacity-50'
              >
                <Square className='w-4 h-4' />
                {createTimingMutation.isPending ? 'Saving...' : 'Stop'}
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

      {/* Table Topics Note */}
      {selectedSegment && isTableTopicsSegment(selectedSegment) && (
        <div className='p-4 bg-amber-50 rounded-lg text-sm text-amber-700'>
          <p className='font-medium mb-1'>Table Topics Session</p>
          <p>
            For multiple speakers, time each one individually. The batch timing
            feature will be available in a future update.
          </p>
        </div>
      )}
    </div>
  );
}
