import {
  TimingIF,
  TimingsListResponseIF,
  TimingCreateIF,
  TimingBatchCreateIF,
} from '../interfaces';
import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

// Shared dot color mapping for timing status indicators
export const dotColors: Record<string, string> = {
  gray: 'bg-gray-400',
  green: 'bg-green-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500',
  bell: 'bg-red-600',
};

/**
 * Fetches all timing records for a meeting
 * @param meetingId The meeting ID
 * @returns TimingsListResponse with can_control flag and timings
 */
export const getTimings = requestTemplate(
  (meetingId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/timings`,
    method: 'GET',
    headers: new Headers({
      Accept: 'application/json',
    }),
  }),
  async (response: Response): Promise<TimingsListResponseIF> => {
    const data = await responseHandlerTemplate(response);
    return data as TimingsListResponseIF;
  },
  null,
  true, // Requires authentication
  true // Soft auth - don't throw if no token
);

/**
 * Creates a single timing record
 * Only the Timer role holder can create timing records
 * @param meetingId The meeting ID
 * @param timingData The timing data
 * @returns The created timing record
 */
export const createTiming = requestTemplate(
  (meetingId: string, timingData: TimingCreateIF) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/timings`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify(timingData),
  }),
  async (
    response: Response
  ): Promise<{ success: boolean; timing: TimingIF }> => {
    const data = await responseHandlerTemplate(response);
    return data;
  },
  null,
  true // Requires authentication
);

/**
 * Creates multiple timing records in batch (for Table Topics)
 * Only the Timer role holder can create timing records
 * @param meetingId The meeting ID
 * @param batchData The batch timing data
 * @returns List of created timing records
 */
export const createTimingBatch = requestTemplate(
  (meetingId: string, batchData: TimingBatchCreateIF) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/timings/batch`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify(batchData),
  }),
  async (
    response: Response
  ): Promise<{ success: boolean; timings: TimingIF[] }> => {
    const data = await responseHandlerTemplate(response);
    return data;
  },
  null,
  true // Requires authentication
);

/**
 * Helper to get timing for a specific segment
 * @param timings All timings
 * @param segmentId The segment ID to find
 * @returns The timing(s) for this segment or undefined
 */
export function getTimingsForSegment(
  timings: TimingIF[] | undefined,
  segmentId: string
): TimingIF[] {
  return timings?.filter((t) => t.segment_id === segmentId) || [];
}

/**
 * Get card signal times for a segment based on planned duration
 * Based on Toastmasters card signal standards
 * @param plannedMinutes The planned duration in minutes
 * @returns Object with green, yellow, red card times in seconds
 */
export function getCardTimes(plannedMinutes: number): {
  green: number;
  yellow: number;
  red: number;
} {
  const planned = plannedMinutes * 60; // in seconds

  if (plannedMinutes <= 3) {
    return { green: planned - 60, yellow: planned - 30, red: planned };
  } else if (plannedMinutes <= 10) {
    return { green: planned - 120, yellow: planned - 60, red: planned };
  } else {
    return { green: planned - 300, yellow: planned - 120, red: planned };
  }
}

/**
 * Get the current countdown zone based on elapsed time
 * @param plannedMinutes The planned duration in minutes
 * @param elapsedSeconds The elapsed time in seconds
 * @returns The current zone color
 */
export function getCountdownZone(
  plannedMinutes: number,
  elapsedSeconds: number
): 'gray' | 'green' | 'yellow' | 'red' | 'overtime' {
  const cards = getCardTimes(plannedMinutes);

  if (elapsedSeconds < cards.green) return 'gray';
  if (elapsedSeconds < cards.yellow) return 'green';
  if (elapsedSeconds < cards.red) return 'yellow';
  if (elapsedSeconds < cards.red + 30) return 'red';
  return 'overtime';
}

/**
 * Format duration in seconds to mm:ss string
 * @param seconds Duration in seconds
 * @returns Formatted string like "05:30"
 */
export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format time from ISO string to HH:MM:SS format
 * @param isoString ISO timestamp string
 * @returns Formatted time like "20:15:30"
 */
export function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * Format relative duration with +/- sign
 * @param actualSeconds Actual duration in seconds
 * @param plannedMinutes Planned duration in minutes
 * @returns Formatted string like "+ 01:30" or "- 00:45"
 */
export function formatRelativeDuration(
  actualSeconds: number,
  plannedMinutes: number
): string {
  const plannedSeconds = plannedMinutes * 60;
  const diff = actualSeconds - plannedSeconds;
  const absDiff = Math.abs(diff);
  const sign = diff >= 0 ? '+' : '-';
  return `${sign} ${formatDuration(absDiff)}`;
}

/**
 * Get tooltip content for a timing record
 * @param timing The timing record
 * @returns Tooltip string like "20:12 - 20:19 (06m48s)"
 */
export function getTimingTooltip(timing: TimingIF): string {
  const start = formatTime(timing.actual_start_time);
  const end = formatTime(timing.actual_end_time);
  const mins = Math.floor(timing.actual_duration_seconds / 60);
  const secs = timing.actual_duration_seconds % 60;
  return `${start} - ${end} (${mins.toString().padStart(2, '0')}m${secs.toString().padStart(2, '0')}s)`;
}
