'use client';

import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import { useAtom } from 'jotai';
import { Play, Square, Bell, X } from 'lucide-react';
import { SegmentIF, TimingIF, TimingBatchItemIF } from '@/interfaces';
import {
  dotColors,
  formatDuration,
  formatTime,
  formatRelativeDuration,
  getTimingDotColor,
  TABLE_TOPICS_SPEAKER_MINUTES,
} from '@/utils/timing';
import { useCreateTimingBatch } from '@/hooks/useSegmentTimings';
import {
  cachedTimingsAtom,
  runningTimerAtom,
  CachedTiming,
} from '@/atoms/timerAtoms';
import toast from 'react-hot-toast';
import { CardSignals, TimerDisplay } from './TimerComponents';

interface TableTopicsTimerProps {
  meetingId: string;
  segment: SegmentIF;
  timings: TimingIF[]; // Existing timings for this segment from server
}

// Convert server TimingIF to local CachedTiming format
function serverTimingToCached(timing: TimingIF): CachedTiming {
  return {
    name: timing.name || '',
    plannedMinutes: timing.planned_duration_minutes,
    actualSeconds: timing.actual_duration_seconds,
    startTime: new Date(timing.actual_start_time).getTime(),
    endTime: new Date(timing.actual_end_time).getTime(),
    dotColor: timing.dot_color,
  };
}

export function TableTopicsTimer({
  meetingId,
  segment,
  timings,
}: TableTopicsTimerProps) {
  const [speakerNameInput, setSpeakerNameInput] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [showRelative, setShowRelative] = useState(false);

  // Track if we've initialized from server data for this segment
  const initializedSegmentRef = useRef<string | null>(null);

  // Use Jotai atoms for persistent state
  const [allCachedTimings, setAllCachedTimings] = useAtom(cachedTimingsAtom);
  const [runningTimer, setRunningTimer] = useAtom(runningTimerAtom);

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

  const cachedTimings = useMemo(
    () => allCachedTimings[segment.id] || [],
    [allCachedTimings, segment.id]
  );

  const setCachedTimings = useCallback(
    (updater: CachedTiming[] | ((prev: CachedTiming[]) => CachedTiming[])) => {
      setAllCachedTimings((prev) => ({
        ...prev,
        [segment.id]:
          typeof updater === 'function'
            ? updater(prev[segment.id] || [])
            : updater,
      }));
    },
    [segment.id, setAllCachedTimings]
  );

  // Initialize from server timings when segment changes or on first load
  useEffect(() => {
    // Only initialize if we haven't already for this segment
    if (initializedSegmentRef.current === segment.id) {
      return;
    }

    // Check if this segment has been initialized (key exists in allCachedTimings)
    // This distinguishes "never loaded" from "user deleted all speakers"
    const hasBeenInitialized = segment.id in allCachedTimings;

    if (!hasBeenInitialized) {
      // First time loading this segment - populate from server timings
      const converted = timings.map(serverTimingToCached);
      setAllCachedTimings((prev) => ({
        ...prev,
        [segment.id]: converted,
      }));
    }

    initializedSegmentRef.current = segment.id;
  }, [segment.id, timings, allCachedTimings, setAllCachedTimings]);

  const createBatchMutation = useCreateTimingBatch(meetingId);

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

    // Capture values before clearing state (also helps TypeScript narrow types)
    const startTime = runningTimer.startedAt;
    const speakerName = runningTimer.speakerName.trim();
    const endTime = Date.now();
    const actualSeconds = Math.floor((endTime - startTime) / 1000);
    const dotColor = getTimingDotColor(plannedMinutes, actualSeconds);

    setCachedTimings((prev) => [
      ...prev,
      {
        name: speakerName,
        plannedMinutes,
        actualSeconds,
        startTime,
        endTime,
        dotColor,
      },
    ]);

    setRunningTimer(null);
    setElapsed(0);
    setSpeakerNameInput('');
  }, [runningTimer, plannedMinutes, setCachedTimings, setRunningTimer]);

  const handleRemoveCached = useCallback(
    (index: number) => {
      setCachedTimings((prev) => prev.filter((_, i) => i !== index));
    },
    [setCachedTimings]
  );

  const handleSave = useCallback(async () => {
    const batchData = {
      segment_id: segment.id,
      timings: cachedTimings.map(
        (t): TimingBatchItemIF => ({
          name: t.name,
          planned_duration_minutes: t.plannedMinutes,
          actual_start_time: new Date(t.startTime).toISOString(),
          actual_end_time: new Date(t.endTime).toISOString(),
        })
      ),
    };

    try {
      await createBatchMutation.mutateAsync(batchData);
      if (cachedTimings.length === 0) {
        toast.success('Cleared all timings');
      } else {
        toast.success(`Saved ${cachedTimings.length} timing(s)`);
      }
      // Keep the list visible so user can continue editing and save again
    } catch (error) {
      toast.error('Failed to save timings');
      console.error('Failed to save batch timings:', error);
    }
  }, [cachedTimings, segment.id, createBatchMutation]);

  return (
    <div className='space-y-4'>
      {/* Main Timer Card - same layout as regular segment */}
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

        {/* Control Button */}
        <div className='flex justify-center mt-2'>
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
        </div>
      </div>

      {/* Cached Timings List - always visible */}
      <div className='bg-white border border-gray-200 rounded-lg p-4'>
        <h4 className='text-xs font-medium text-gray-500 mb-3'>
          Completed ({cachedTimings.length})
        </h4>
        {cachedTimings.length === 0 ? (
          <p className='text-xs text-gray-400 text-center py-2'>
            No speakers timed yet
          </p>
        ) : (
          <div className='space-y-1.5'>
            {cachedTimings.map((timing, index) => {
              const startTimeStr = formatTime(
                new Date(timing.startTime).toISOString()
              );
              const endTimeStr = formatTime(
                new Date(timing.endTime).toISOString()
              );
              const tooltip = `${startTimeStr} - ${endTimeStr}`;

              return (
                <div
                  key={index}
                  className='flex items-center justify-between py-1.5 px-3 bg-gray-50 rounded-lg'
                  title={tooltip}
                >
                  <div className='flex items-center gap-2 min-w-0'>
                    {timing.dotColor === 'bell' ? (
                      <Bell className='w-3 h-3 text-red-600 fill-red-600 flex-shrink-0' />
                    ) : (
                      <span
                        className={`w-2.5 h-2.5 rounded-full ${dotColors[timing.dotColor]} flex-shrink-0`}
                      />
                    )}
                    <span className='text-xs sm:text-sm text-gray-800 truncate'>
                      {timing.name}
                    </span>
                  </div>
                  <div className='flex items-center gap-1.5 flex-shrink-0'>
                    <button
                      onClick={() => setShowRelative(!showRelative)}
                      className='flex items-center gap-1 hover:opacity-70 transition-opacity'
                    >
                      <span className='text-xs sm:text-sm font-mono text-gray-600 tabular-nums'>
                        {showRelative
                          ? formatRelativeDuration(
                              timing.actualSeconds,
                              timing.plannedMinutes
                            )
                          : formatDuration(timing.actualSeconds)}
                      </span>
                      <span className='text-[10px] sm:text-xs text-gray-400'>
                        / {timing.plannedMinutes}m
                      </span>
                    </button>
                    <button
                      onClick={() => handleRemoveCached(index)}
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

        {/* Save Button - saves current list state (including empty = delete all) */}
        <button
          onClick={handleSave}
          disabled={createBatchMutation.isPending || isThisSegmentRunning}
          className='mt-4 w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
        >
          {createBatchMutation.isPending ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  );
}
