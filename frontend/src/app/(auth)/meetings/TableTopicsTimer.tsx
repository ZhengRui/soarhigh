'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Play, Square, ChevronLeft, ChevronRight } from 'lucide-react';
import { SegmentIF } from '@/interfaces';
import {
  getTimingDotColor,
  TABLE_TOPICS_SPEAKER_MINUTES,
} from '@/utils/timing';
import { CachedTimingsState, CachedTimingEntry } from '@/utils/timingStorage';
import toast from 'react-hot-toast';
import { CardSignals, TimerDisplay } from './TimerComponents';
import { RunningTimerState } from './TimerTab';

interface TableTopicsTimerProps {
  segment: SegmentIF;
  // Lifted state from TimerTab
  runningTimer: RunningTimerState | null;
  setRunningTimer: (state: RunningTimerState | null) => void;
  // Cached timings from localStorage (managed by TimerTab)
  cachedTimings: CachedTimingsState;
  updateCache: (cache: CachedTimingsState) => void;
  // Navigation
  canGoPrev: boolean;
  canGoNext: boolean;
  onGoPrev: () => void;
  onGoNext: () => void;
}

export function TableTopicsTimer({
  segment,
  runningTimer,
  setRunningTimer,
  cachedTimings,
  updateCache,
  canGoPrev,
  canGoNext,
  onGoPrev,
  onGoNext,
}: TableTopicsTimerProps) {
  const [speakerNameInput, setSpeakerNameInput] = useState('');
  const [elapsed, setElapsed] = useState(0);

  // Check if this segment's timer is running
  const isThisSegmentRunning =
    runningTimer?.segmentId === segment.id && runningTimer.isRunning;
  const startedAt = isThisSegmentRunning ? runningTimer.startedAt : null;
  const speakerName = isThisSegmentRunning
    ? runningTimer.speakerName
    : speakerNameInput;

  // Check if another segment is timing
  const isOtherSegmentRunning =
    runningTimer?.isRunning && runningTimer.segmentId !== segment.id;

  // Update cached entries for this segment
  const setCachedEntries = useCallback(
    (
      updater:
        | CachedTimingEntry[]
        | ((prev: CachedTimingEntry[]) => CachedTimingEntry[])
    ) => {
      const currentEntries = cachedTimings[segment.id]?.entries || [];
      const newEntries =
        typeof updater === 'function' ? updater(currentEntries) : updater;

      if (newEntries.length === 0) {
        // Remove segment from cache if empty
        const { [segment.id]: _removed, ...rest } = cachedTimings;
        void _removed; // Suppress unused variable warning
        updateCache(rest);
      } else {
        updateCache({
          ...cachedTimings,
          [segment.id]: {
            segmentId: segment.id,
            segmentType: segment.type,
            entries: newEntries,
          },
        });
      }
    },
    [segment.id, segment.type, cachedTimings, updateCache]
  );

  // Fixed 2 minutes per speaker
  const plannedMinutes = TABLE_TOPICS_SPEAKER_MINUTES;

  // Update elapsed time when running
  useEffect(() => {
    if (!isThisSegmentRunning || !startedAt) return;

    // Immediately calculate elapsed on mount
    setElapsed(Math.floor((Date.now() - startedAt) / 1000));

    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 100);

    return () => clearInterval(interval);
  }, [isThisSegmentRunning, startedAt]);

  const handleStart = useCallback(() => {
    const name = speakerNameInput.trim();
    if (!name) {
      toast.error('Please enter speaker name');
      return;
    }
    setRunningTimer({
      segmentId: segment.id,
      isRunning: true,
      startedAt: Date.now(),
      speakerName: name,
    });
    setElapsed(0);
  }, [speakerNameInput, segment.id, setRunningTimer]);

  const handleStop = useCallback(() => {
    if (!runningTimer?.startedAt) return;

    // Capture values before clearing state
    const startTime = runningTimer.startedAt;
    const speakerName = runningTimer.speakerName.trim();
    const endTime = Date.now();
    const actualSeconds = Math.floor((endTime - startTime) / 1000);
    const dotColor = getTimingDotColor(plannedMinutes, actualSeconds);

    setCachedEntries((prev) => [
      ...prev,
      {
        name: speakerName,
        plannedDurationMinutes: plannedMinutes,
        startedAt: startTime,
        endedAt: endTime,
        dotColor,
      },
    ]);

    setRunningTimer(null);
    setElapsed(0);
    setSpeakerNameInput('');
  }, [runningTimer, plannedMinutes, setCachedEntries, setRunningTimer]);

  return (
    <div className='bg-white border border-gray-200 rounded-lg p-5 sm:p-6'>
      {/* Header: same layout as regular segment */}
      <div className='text-center sm:text-left sm:flex sm:items-start sm:justify-between sm:gap-4 mb-4'>
        {/* Left: Segment info + speaker input */}
        <div className='space-y-2 sm:space-y-1'>
          <h3 className='text-sm font-medium text-gray-900 truncate'>
            {segment.type}
          </h3>
          <div className='my-2 sm:my-0 sm:mt-1.5'>
            <input
              type='text'
              value={speakerName}
              onChange={(e) => setSpeakerNameInput(e.target.value)}
              placeholder='Speaker name'
              disabled={isThisSegmentRunning || isOtherSegmentRunning}
              className='w-full sm:w-48 px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed'
            />
          </div>
        </div>
        {/* Right: Checkpoints */}
        <div className='mt-2 sm:mt-0 sm:text-right space-y-1 sm:space-y-0'>
          <CardSignals plannedMinutes={plannedMinutes} />
          {/* Reserve height for consistency */}
          <div className='text-xs text-gray-400 h-8 flex flex-col items-center sm:items-end justify-start sm:mt-1'>
            <span className='text-gray-400 font-mono tabular-nums'>
              {TABLE_TOPICS_SPEAKER_MINUTES}min per speaker
            </span>
          </div>
        </div>
      </div>

      {/* Timer Display */}
      <TimerDisplay
        elapsed={elapsed}
        plannedMinutes={plannedMinutes}
        isRunning={isThisSegmentRunning}
      />

      {/* Control Buttons */}
      <div className='flex items-center justify-center gap-3 mt-2'>
        {/* Prev Button */}
        <button
          onClick={onGoPrev}
          disabled={!canGoPrev || isThisSegmentRunning}
          className='flex items-center justify-center w-10 h-10 rounded-full text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'
          title='Previous segment'
        >
          <ChevronLeft className='w-5 h-5' />
        </button>

        {/* Start/Stop Button */}
        {!isThisSegmentRunning ? (
          <button
            onClick={handleStart}
            disabled={!speakerNameInput.trim() || isOtherSegmentRunning}
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

        {/* Next Button */}
        <button
          onClick={onGoNext}
          disabled={!canGoNext || isThisSegmentRunning}
          className='flex items-center justify-center w-10 h-10 rounded-full text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'
          title='Next segment'
        >
          <ChevronRight className='w-5 h-5' />
        </button>
      </div>
    </div>
  );
}
