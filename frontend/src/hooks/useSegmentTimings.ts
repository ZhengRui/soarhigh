import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getTimings } from '@/utils/timing';
import { TimingsListResponseIF } from '@/interfaces';

/**
 * Hook to fetch timings for a meeting
 * @param meetingId The meeting ID
 * @returns Query result with timings data and can_control flag
 */
export function useSegmentTimings(meetingId?: string) {
  return useQuery<TimingsListResponseIF>({
    queryKey: ['timings', meetingId],
    queryFn: () => {
      if (!meetingId) throw new Error('Meeting ID is required');
      return getTimings(meetingId);
    },
    enabled: !!meetingId,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}
