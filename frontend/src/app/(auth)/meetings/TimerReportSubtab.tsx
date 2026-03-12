'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { TimingIF, SegmentIF } from '@/interfaces';
import {
  dotColors,
  getTimingTooltip,
  formatDuration,
  formatRelativeDuration,
  deleteTiming,
  createTiming,
  updateTiming,
  parseDurationToMinutes,
  TABLE_TOPICS_SEGMENT_TYPE,
  TABLE_TOPICS_SPEAKER_MINUTES,
} from '@/utils/timing';
import { Bell, Clock, PlusCircle, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import type { ReportSortOrder } from './TimerTab';
import { TimingConfirmDialog } from './TimingConfirmDialog';

interface TimerReportSubtabProps {
  meetingId: string;
  segments: SegmentIF[];
  timings: TimingIF[];
  canControl: boolean;
  sortOrder?: ReportSortOrder;
}

interface TimingModalState {
  visible: boolean;
  mode: 'add' | 'edit' | 'view';
  timingId: string | null;
  segmentId: string;
  speakerName: string;
  dateStr: string;
  startTimeStr: string;
  durationStr: string;
}

const emptyTimingModal: TimingModalState = {
  visible: false,
  mode: 'add',
  timingId: null,
  segmentId: '',
  speakerName: '',
  dateStr: '',
  startTimeStr: '',
  durationStr: '03:00',
};

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
  gray: 0,
  green: 1,
  yellow: 2,
  red: 3,
  bell: 4,
};

function formatDateInput(isoString: string): string {
  const date = new Date(isoString);
  return formatDateValue(date);
}

function formatDateValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatTimeInput(isoString: string): string {
  const date = new Date(isoString);
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

function formatDurationInput(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function buildErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  return fallback;
}

function isExpectedTimingSaveError(error: unknown): boolean {
  const message = buildErrorMessage(error, '');
  return (
    message.includes('already exists in this Table Topics session') ||
    message.includes('Delete it first if you want to replace it.')
  );
}

// Sort timings by status, then by signed distance to planned duration.
function sortByStatus(timings: TimingIF[]): TimingIF[] {
  return [...timings].sort((a, b) => {
    const statusDiff = statusOrder[a.dot_color] - statusOrder[b.dot_color];
    if (statusDiff !== 0) return statusDiff;

    const aPlannedSeconds = a.planned_duration_minutes * 60;
    const bPlannedSeconds = b.planned_duration_minutes * 60;
    const aDistance = a.actual_duration_seconds - aPlannedSeconds;
    const bDistance = b.actual_duration_seconds - bPlannedSeconds;
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
  const [showRelative, setShowRelative] = useState(false);
  const [timingToDelete, setTimingToDelete] = useState<TimingIF | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [timingModal, setTimingModal] =
    useState<TimingModalState>(emptyTimingModal);

  const queryClient = useQueryClient();

  const segmentMap = useMemo(
    () => new Map(segments.map((segment) => [segment.id, segment])),
    [segments]
  );
  const displayedTimings =
    sortOrder === 'chronological' ? sortByTime(timings) : sortByStatus(timings);
  const colorCounts = countTimingsByColor(timings);
  const colorOrder = ['gray', 'green', 'yellow', 'red', 'bell'] as const;

  const segmentOptions = segments.map((segment) => {
    const hasSavedTiming =
      segment.type !== TABLE_TOPICS_SEGMENT_TYPE &&
      timings.some((timing) => timing.segment_id === segment.id);
    return {
      id: segment.id,
      label: segment.role_taker?.name
        ? `${segment.type} (${segment.role_taker.name})`
        : segment.type,
      disabled: hasSavedTiming,
    };
  });

  const getPlannedDurationMinutes = useCallback(
    (segmentId: string): number => {
      const segment = segmentMap.get(segmentId);
      if (!segment) {
        return 3;
      }

      return segment.type === TABLE_TOPICS_SEGMENT_TYPE
        ? TABLE_TOPICS_SPEAKER_MINUTES
        : parseDurationToMinutes(segment.duration);
    },
    [segmentMap]
  );

  const openTimingModal = useCallback(
    (timing: TimingIF) => {
      setTimingModal({
        visible: true,
        mode: canControl ? 'edit' : 'view',
        timingId: timing.id || null,
        segmentId: timing.segment_id,
        speakerName: timing.name || '',
        dateStr: formatDateInput(timing.actual_start_time),
        startTimeStr: formatTimeInput(timing.actual_start_time),
        durationStr: formatDurationInput(timing.actual_duration_seconds),
      });
    },
    [canControl]
  );

  const openAddModal = useCallback(() => {
    const defaultSegment = segmentOptions.find((option) => !option.disabled);
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const defaultSegmentMeta = defaultSegment
      ? segmentMap.get(defaultSegment.id)
      : undefined;

    setTimingModal({
      visible: true,
      mode: 'add',
      timingId: null,
      segmentId: defaultSegment?.id || '',
      speakerName: defaultSegmentMeta?.role_taker?.name || '',
      dateStr: formatDateValue(now),
      startTimeStr: `${hours}:${minutes}:${seconds}`,
      durationStr: '03:00',
    });
  }, [segmentMap, segmentOptions]);

  const closeTimingModal = useCallback(() => {
    setTimingModal(emptyTimingModal);
  }, []);

  const handleDelete = useCallback(async () => {
    if (!timingToDelete?.id) return;

    setIsDeleting(true);
    try {
      await deleteTiming(meetingId, timingToDelete.id);
      await queryClient.invalidateQueries({ queryKey: ['timings', meetingId] });
      toast.success('Timing deleted');
      setTimingToDelete(null);
    } catch (error) {
      toast.error(buildErrorMessage(error, 'Failed to delete timing'));
      console.error('Failed to delete timing:', error);
    } finally {
      setIsDeleting(false);
    }
  }, [meetingId, queryClient, timingToDelete]);

  const handleSave = useCallback(async () => {
    const {
      mode,
      timingId,
      segmentId,
      speakerName,
      dateStr,
      startTimeStr,
      durationStr,
    } = timingModal;

    if (mode === 'view') {
      return;
    }

    if (!segmentId) {
      toast.error('Please select a segment');
      return;
    }

    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      toast.error('Invalid date');
      return;
    }

    if (!/^\d{1,2}:\d{2}(:\d{2})?$/.test(startTimeStr)) {
      toast.error('Invalid start time');
      return;
    }

    if (!/^\d{1,2}:\d{2}$/.test(durationStr)) {
      toast.error('Invalid duration');
      return;
    }

    const normalizedTime =
      startTimeStr.length === 5 ? `${startTimeStr}:00` : startTimeStr;
    const [hours, minutes, seconds] = normalizedTime.split(':').map(Number);
    const [durationMinutes, durationSeconds] = durationStr
      .split(':')
      .map(Number);

    if (
      [hours, minutes, seconds, durationMinutes, durationSeconds].some(
        (value) => Number.isNaN(value)
      ) ||
      hours > 23 ||
      minutes > 59 ||
      seconds > 59 ||
      durationSeconds > 59
    ) {
      toast.error('Invalid time values');
      return;
    }

    const startDate = new Date(
      `${dateStr}T${String(hours).padStart(2, '0')}:${String(minutes).padStart(
        2,
        '0'
      )}:${String(seconds).padStart(2, '0')}`
    );
    if (Number.isNaN(startDate.getTime())) {
      toast.error('Invalid date/time');
      return;
    }

    const totalDurationSeconds = durationMinutes * 60 + durationSeconds;
    if (totalDurationSeconds <= 0) {
      toast.error('Duration must be greater than zero');
      return;
    }

    const actualStartTime = startDate.toISOString();
    const actualEndTime = new Date(
      startDate.getTime() + totalDurationSeconds * 1000
    ).toISOString();
    const plannedDurationMinutes = getPlannedDurationMinutes(segmentId);

    setIsSaving(true);
    try {
      if (mode === 'add') {
        await createTiming(meetingId, {
          segment_id: segmentId,
          name: speakerName.trim() || null,
          planned_duration_minutes: plannedDurationMinutes,
          actual_start_time: actualStartTime,
          actual_end_time: actualEndTime,
        });
      } else {
        if (!timingId) {
          throw new Error('Missing timing ID');
        }

        await updateTiming(meetingId, timingId, {
          name: speakerName.trim() || null,
          planned_duration_minutes: plannedDurationMinutes,
          actual_start_time: actualStartTime,
          actual_end_time: actualEndTime,
        });
      }

      await queryClient.invalidateQueries({ queryKey: ['timings', meetingId] });
      setTimingModal(emptyTimingModal);
      toast.success(mode === 'add' ? 'Timing added' : 'Timing updated');
    } catch (error) {
      toast.error(buildErrorMessage(error, 'Failed to save timing'));
      if (!isExpectedTimingSaveError(error)) {
        console.error('Failed to save timing:', error);
      }
    } finally {
      setIsSaving(false);
    }
  }, [getPlannedDurationMinutes, meetingId, queryClient, timingModal]);

  const selectedSegment = segmentMap.get(timingModal.segmentId);
  const modalReadOnly = timingModal.mode === 'view';
  const deleteCandidate =
    timingModal.timingId &&
    timings.find((timing) => timing.id === timingModal.timingId);

  const summaryItems = colorOrder.map((color) => ({
    color,
    count: colorCounts[color],
    label: statusLabels[color],
  }));

  return (
    <div className='space-y-4'>
      {timings.length > 0 && (
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
      )}

      {timings.length === 0 ? (
        <div className='bg-gray-50 border border-dashed border-gray-300 rounded-lg p-8 flex items-center justify-center'>
          <div className='text-center text-gray-500'>
            <Clock className='w-12 h-12 mx-auto mb-2 text-gray-300' />
            <p className='text-sm'>No timing records for this meeting</p>
          </div>
        </div>
      ) : (
        <div className='space-y-1.5'>
          {displayedTimings.map((timing) => {
            const segment = segmentMap.get(timing.segment_id);
            const color = timing.dot_color;
            const name = timing.name || segment?.role_taker?.name;
            const segmentType = segment?.type;

            return (
              <div
                key={timing.id}
                role='button'
                tabIndex={0}
                onClick={() => openTimingModal(timing)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openTimingModal(timing);
                  }
                }}
                className='w-full bg-white border border-gray-200 rounded-lg py-2 px-3 flex items-center justify-between text-left hover:border-gray-300 transition-colors'
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
                    type='button'
                    onClick={(event) => {
                      event.stopPropagation();
                      setShowRelative((prev) => !prev);
                    }}
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
                </div>
              </div>
            );
          })}
        </div>
      )}

      {canControl && (
        <button
          type='button'
          onClick={openAddModal}
          className='w-full bg-white border border-dashed border-gray-300 rounded-lg py-3 px-4 flex items-center justify-center gap-2 text-sm font-medium text-indigo-700 hover:border-indigo-400 hover:text-indigo-800 transition-colors'
        >
          <PlusCircle className='w-4 h-4' />
          Add timing record
        </button>
      )}

      {timingModal.visible &&
        typeof window !== 'undefined' &&
        createPortal(
          <div
            className='fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]'
            onClick={closeTimingModal}
          >
            <div
              className='bg-white rounded-lg p-6 mx-4 w-full max-w-md shadow-xl'
              onClick={(event) => event.stopPropagation()}
            >
              <div className='flex items-center justify-between mb-4'>
                <h4 className='text-base font-medium text-gray-900'>
                  {timingModal.mode === 'add'
                    ? 'Add Timing'
                    : modalReadOnly
                      ? 'Timing Details'
                      : 'Edit Timing'}
                </h4>
                <button
                  type='button'
                  onClick={closeTimingModal}
                  className='p-1 text-gray-400 hover:text-gray-600 transition-colors'
                >
                  <X className='w-4 h-4' />
                </button>
              </div>

              <div className='space-y-4'>
                <label className='block'>
                  <span className='text-xs font-medium text-gray-500'>
                    Segment
                  </span>
                  {timingModal.mode === 'add' ? (
                    <select
                      value={timingModal.segmentId}
                      onChange={(event) => {
                        const segment = segmentMap.get(event.target.value);
                        setTimingModal((current) => ({
                          ...current,
                          segmentId: event.target.value,
                          speakerName: segment?.role_taker?.name || '',
                        }));
                      }}
                      disabled={modalReadOnly}
                      className='mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500'
                    >
                      <option value=''>Select segment</option>
                      {segmentOptions.map((option) => (
                        <option
                          key={option.id}
                          value={option.id}
                          disabled={option.disabled}
                        >
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className='mt-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 bg-gray-50'>
                      {selectedSegment?.type || 'Unknown'}
                    </div>
                  )}
                </label>

                <label className='block'>
                  <span className='text-xs font-medium text-gray-500'>
                    Speaker
                  </span>
                  {modalReadOnly ? (
                    <div className='mt-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 bg-gray-50'>
                      {timingModal.speakerName || '-'}
                    </div>
                  ) : (
                    <input
                      type='text'
                      value={timingModal.speakerName}
                      onChange={(event) =>
                        setTimingModal((current) => ({
                          ...current,
                          speakerName: event.target.value,
                        }))
                      }
                      className='mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500'
                    />
                  )}
                </label>

                <div className='grid grid-cols-1 sm:grid-cols-2 gap-4'>
                  <label className='block'>
                    <span className='text-xs font-medium text-gray-500'>
                      Date
                    </span>
                    {modalReadOnly ? (
                      <div className='mt-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 bg-gray-50'>
                        {timingModal.dateStr}
                      </div>
                    ) : (
                      <input
                        type='date'
                        value={timingModal.dateStr}
                        onChange={(event) =>
                          setTimingModal((current) => ({
                            ...current,
                            dateStr: event.target.value,
                          }))
                        }
                        className='mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500'
                      />
                    )}
                  </label>

                  <label className='block'>
                    <span className='text-xs font-medium text-gray-500'>
                      Start Time
                    </span>
                    {modalReadOnly ? (
                      <div className='mt-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 bg-gray-50'>
                        {timingModal.startTimeStr}
                      </div>
                    ) : (
                      <input
                        type='time'
                        step={1}
                        value={timingModal.startTimeStr}
                        onChange={(event) =>
                          setTimingModal((current) => ({
                            ...current,
                            startTimeStr: event.target.value,
                          }))
                        }
                        className='mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500'
                      />
                    )}
                  </label>
                </div>

                <label className='block'>
                  <span className='text-xs font-medium text-gray-500'>
                    Duration (MM:SS)
                  </span>
                  {modalReadOnly ? (
                    <div className='mt-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 bg-gray-50'>
                      {timingModal.durationStr}
                    </div>
                  ) : (
                    <input
                      type='text'
                      value={timingModal.durationStr}
                      onChange={(event) =>
                        setTimingModal((current) => ({
                          ...current,
                          durationStr: event.target.value.replace(
                            /[^\d:]/g,
                            ''
                          ),
                        }))
                      }
                      className='mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500'
                    />
                  )}
                </label>
              </div>

              {!modalReadOnly && (
                <div className='flex items-center justify-between gap-3 mt-6'>
                  {timingModal.mode === 'edit' ? (
                    <button
                      type='button'
                      onClick={() => {
                        if (deleteCandidate) {
                          setTimingModal(emptyTimingModal);
                          setTimingToDelete(deleteCandidate);
                        }
                      }}
                      className='px-4 py-2 text-sm font-medium text-red-600 hover:text-red-700 transition-colors'
                    >
                      Delete
                    </button>
                  ) : (
                    <div />
                  )}

                  <button
                    type='button'
                    onClick={handleSave}
                    disabled={isSaving}
                    className='px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50'
                  >
                    {isSaving ? 'Saving...' : 'Save'}
                  </button>
                </div>
              )}
            </div>
          </div>,
          document.body
        )}

      <TimingConfirmDialog
        visible={Boolean(timingToDelete)}
        title='Delete timing record?'
        message={
          timingToDelete ? (
            <>
              This will permanently delete the timing record for{' '}
              <span className='font-medium'>
                {timingToDelete.name ||
                  segmentMap.get(timingToDelete.segment_id)?.role_taker?.name ||
                  segmentMap.get(timingToDelete.segment_id)?.type ||
                  'this segment'}
              </span>
              . This action cannot be undone.
            </>
          ) : (
            ''
          )
        }
        confirmText={isDeleting ? 'Deleting...' : 'Delete'}
        confirmDanger
        confirmDisabled={isDeleting}
        cancelDisabled={isDeleting}
        onCancel={() => setTimingToDelete(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
