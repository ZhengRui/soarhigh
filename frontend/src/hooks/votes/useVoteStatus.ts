import { useQuery } from '@tanstack/react-query';
import { VoteStatusIF } from '@/interfaces';
import { getVoteStatus } from '@/utils/votes';

/**
 * Hook to fetch vote status for a meeting
 * @param meetingId The meeting ID
 * @returns Query result with vote status data
 */
export function useVoteStatus(meetingId: string) {
  return useQuery<VoteStatusIF>({
    queryKey: ['voteStatus', meetingId],
    queryFn: () => getVoteStatus(meetingId),
    enabled: !!meetingId,
    refetchOnWindowFocus: false,
  });
}
