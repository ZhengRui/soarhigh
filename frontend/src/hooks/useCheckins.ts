import {
  keepPreviousData,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { getCheckins, resetCheckin } from '@/utils/checkin';
import { CheckinIF } from '@/interfaces';

/**
 * Hook to fetch checkins for a meeting
 * @param meetingId The meeting ID
 * @returns Query result with checkins data
 */
export function useCheckins(meetingId?: string) {
  return useQuery<CheckinIF[]>({
    queryKey: ['checkins', meetingId],
    queryFn: () => {
      if (!meetingId) throw new Error('Meeting ID is required');
      return getCheckins(meetingId);
    },
    enabled: !!meetingId,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to reset a segment's checkin
 * @returns Mutation function and state
 */
export function useResetCheckin(meetingId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (segmentId: string) => {
      if (!meetingId) throw new Error('Meeting ID is required');
      return resetCheckin(meetingId, segmentId);
    },
    onSuccess: () => {
      // Invalidate checkins query to refetch
      queryClient.invalidateQueries({ queryKey: ['checkins', meetingId] });
    },
  });
}
