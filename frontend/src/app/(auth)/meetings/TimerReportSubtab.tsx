'use client';

import React, { useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { TimingIF, SegmentIF } from '@/interfaces';
import {
  dotColors,
  getTimingTooltip,
  formatDuration,
  formatRelativeDuration,
  deleteTiming,
} from '@/utils/timing';
import { Bell, Clock, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import type { ReportSortOrder } from './TimerTab';

interface TimerReportSubtabProps {
  meetingId: string;
  segments: SegmentIF[];
  timings: TimingIF[];
  canControl: boolean;
  sortOrder?: ReportSortOrder;
}

// Labels for each status (based on Toastmasters timing)
const statusLabels: Record<string, string> = {
  gray: 'Too Short',
  green: 'Under Used',
  yellow: 'Perfect',
  red: 'Over',
  bell: 'Way Over',
};

// Status order for sorting (by time progression)
const statusOrder: Record<string, number> = {
  gray: 0, // Too Short
  green: 1, // Under Used
  yellow: 2, // Perfect
  red: 3, // Over
  bell: 4, // Way Over
};

// Sort timings by status, then by distance to planned duration
function sortByStatus(timings: TimingIF[]): TimingIF[] {
  return [...timings].sort((a, b) => {
    // First sort by status
    const statusDiff = statusOrder[a.dot_color] - statusOrder[b.dot_color];
    if (statusDiff !== 0) return statusDiff;

    // Within same status, sort by distance to planned duration
    const aPlannedSeconds = a.planned_duration_minutes * 60;
    const bPlannedSeconds = b.planned_duration_minutes * 60;
    const aDistance = Math.abs(a.actual_duration_seconds - aPlannedSeconds);
    const bDistance = Math.abs(b.actual_duration_seconds - bPlannedSeconds);
    return aDistance - bDistance;
  });
}

// Sort timings chronologically by start time
function sortByTime(timings: TimingIF[]): TimingIF[] {
  return [...timings].sort((a, b) => {
    const aTime = a.actual_start_time
      ? new Date(a.actual_start_time).getTime()
      : 0;
    const bTime = b.actual_start_time
      ? new Date(b.actual_start_time).getTime()
      : 0;
    return aTime - bTime;
  });
}

// Count timings by dot color
function countTimingsByColor(timings: TimingIF[]): Record<string, number> {
  const counts: Record<string, number> = {
    gray: 0,
    green: 0,
    yellow: 0,
    red: 0,
    bell: 0,
  };
  for (const timing of timings) {
    if (counts[timing.dot_color] !== undefined) {
      counts[timing.dot_color]++;
    }
  }
  return counts;
}

export function TimerReportSubtab({
  meetingId,
  segments,
  timings,
  canControl,
  sortOrder = 'status',
}: TimerReportSubtabProps) {
  // Toggle between absolute and relative duration display
  const [showRelative, setShowRelative] = useState(false);
  const [timingToDelete, setTimingToDelete] = useState<TimingIF | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const queryClient = useQueryClient();

  // Create a map from segment_id to segment for quick lookup
  const segmentMap = new Map(segments.map((s) => [s.id, s]));

  // Count timings by color for summary pills
  const colorCounts = countTimingsByColor(timings);

  // Order to display groups (by time progression)
  const colorOrder = ['gray', 'green', 'yellow', 'red', 'bell'] as const;

  // Handle delete timing
  const handleDelete = useCallback(async () => {
    if (!timingToDelete) return;

    setIsDeleting(true);
    try {
      await deleteTiming(meetingId, timingToDelete.id!);
      queryClient.invalidateQueries({ queryKey: ['timings', meetingId] });
      toast.success('Timing deleted');
      setTimingToDelete(null);
    } catch (error) {
      toast.error('Failed to delete timing');
      console.error('Failed to delete timing:', error);
    } finally {
      setIsDeleting(false);
    }
  }, [timingToDelete, meetingId, queryClient]);

  if (timings.length === 0) {
    return (
      <div className='bg-gray-50 border border-dashed border-gray-300 rounded-lg p-8 flex items-center justify-center'>
        <div className='text-center text-gray-500'>
          <Clock className='w-12 h-12 mx-auto mb-2 text-gray-300' />
          <p className='text-sm'>No timing records for this meeting</p>
        </div>
      </div>
    );
  }

  // All groups for summary (always show all 5)
  const summaryItems = colorOrder.map((color) => ({
    color,
    count: colorCounts[color],
    label: statusLabels[color],
  }));

  return (
    <div className='space-y-4'>
      {/* Compact Summary Pills - horizontally scrollable */}
      <div
        className='flex gap-2 overflow-x-auto'
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        <style jsx>{`
          div::-webkit-scrollbar {
            display: none;
          }
        `}</style>
        {summaryItems.map(({ color, count, label }) => (
          <div
            key={color}
            className='inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-gray-200 rounded-full text-xs flex-shrink-0'
          >
            {color === 'bell' ? (
              <Bell className='w-3 h-3 text-red-600 fill-red-600' />
            ) : (
              <span
                className={`w-2.5 h-2.5 rounded-full ${dotColors[color]}`}
              />
            )}
            <span className='text-gray-600'>
              {count} {label}
            </span>
          </div>
        ))}
      </div>

      {/* Timing List */}
      <div className='space-y-1.5'>
        {(sortOrder === 'chronological'
          ? sortByTime(timings)
          : sortByStatus(timings)
        ).map((timing) => {
          const segment = segmentMap.get(timing.segment_id);
          const color = timing.dot_color;
          const name = timing.name || segment?.role_taker?.name;
          const segmentType = segment?.type;

          return (
            <div
              key={timing.id}
              className='bg-white border border-gray-200 rounded-lg py-2 px-3 flex items-center justify-between'
              title={getTimingTooltip(timing)}
            >
              <div className='flex items-center gap-2 min-w-0'>
                {color === 'bell' ? (
                  <Bell className='w-3 h-3 text-red-600 fill-red-600 flex-shrink-0' />
                ) : (
                  <span
                    className={`w-2.5 h-2.5 rounded-full ${dotColors[color]} flex-shrink-0`}
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
                          timing.actual_duration_seconds,
                          timing.planned_duration_minutes
                        )
                      : formatDuration(timing.actual_duration_seconds)}
                  </span>
                  <span className='text-[10px] sm:text-[11px] text-gray-400'>
                    / {timing.planned_duration_minutes}m
                  </span>
                </button>
                {canControl && (
                  <button
                    onClick={() => setTimingToDelete(timing)}
                    className='p-1 text-gray-400 hover:text-red-500 transition-colors'
                    title='Delete timing'
                  >
                    <X className='w-3.5 h-3.5' />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Delete Confirmation Dialog */}
      {timingToDelete &&
        typeof window !== 'undefined' &&
        createPortal(
          <div
            className='fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]'
            onClick={() => setTimingToDelete(null)}
          >
            <div
              className='bg-white rounded-lg p-6 mx-4 max-w-sm sm:max-w-md shadow-xl'
              onClick={(e) => e.stopPropagation()}
            >
              <h4 className='text-sm sm:text-base font-medium text-gray-900 mb-2'>
                Delete timing record?
              </h4>
              <p className='text-xs sm:text-sm text-gray-500 mb-4'>
                This will permanently delete the timing record for{' '}
                <span className='font-medium'>
                  {timingToDelete.name ||
                    segmentMap.get(timingToDelete.segment_id)?.role_taker
                      ?.name ||
                    segmentMap.get(timingToDelete.segment_id)?.type ||
                    'this segment'}
                </span>
                . This action cannot be undone.
              </p>
              <div className='flex gap-3 justify-end'>
                <button
                  onClick={() => setTimingToDelete(null)}
                  disabled={isDeleting}
                  className='px-3 py-1.5 text-xs sm:text-sm text-gray-600 hover:text-gray-800 transition-colors disabled:opacity-50'
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className='px-4 py-1.5 text-xs sm:text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50'
                >
                  {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
