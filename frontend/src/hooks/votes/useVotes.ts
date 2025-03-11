import { useQuery } from '@tanstack/react-query';
import { VoteIF } from '@/interfaces';
import { getVotes } from '@/utils/votes';

/**
 * Hook to fetch votes for a meeting
 * @param meetingId The meeting ID
 * @returns Query result with votes data
 */
export function useVotes(meetingId: string) {
  return useQuery<VoteIF[]>({
    queryKey: ['votes', meetingId],
    queryFn: () => getVotes(meetingId, false),
    enabled: !!meetingId,
    refetchOnWindowFocus: false,
  });
}
