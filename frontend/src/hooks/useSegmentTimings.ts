import {
  keepPreviousData,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { getTimings, createTiming, createTimingBatch } from '@/utils/timing';
import {
  TimingCreateIF,
  TimingBatchCreateIF,
  TimingsListResponseIF,
} from '@/interfaces';

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

/**
 * Hook to create a single timing record
 * @param meetingId The meeting ID
 * @returns Mutation function and state
 */
export function useCreateTiming(meetingId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (timingData: TimingCreateIF) => {
      if (!meetingId) throw new Error('Meeting ID is required');
      return createTiming(meetingId, timingData);
    },
    onSuccess: () => {
      // Invalidate timings query to refetch
      queryClient.invalidateQueries({ queryKey: ['timings', meetingId] });
    },
  });
}

/**
 * Hook to create timing records in batch (for Table Topics)
 * @param meetingId The meeting ID
 * @returns Mutation function and state
 */
export function useCreateTimingBatch(meetingId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (batchData: TimingBatchCreateIF) => {
      if (!meetingId) throw new Error('Meeting ID is required');
      return createTimingBatch(meetingId, batchData);
    },
    onSuccess: () => {
      // Invalidate timings query to refetch
      queryClient.invalidateQueries({ queryKey: ['timings', meetingId] });
    },
  });
}
