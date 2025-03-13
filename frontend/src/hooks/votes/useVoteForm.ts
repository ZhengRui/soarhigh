import { useQuery } from '@tanstack/react-query';
import { CategoryCandidatesIF } from '@/interfaces';
import { getVotes } from '@/utils/votes';

/**
 * Hook to fetch vote form data for a meeting
 * @param meetingId The meeting ID
 * @returns Query result with vote form data (categories and candidates)
 */
export function useVoteForm(meetingId: string) {
  return useQuery<CategoryCandidatesIF[]>({
    queryKey: ['voteForm', meetingId],
    queryFn: () => getVotes(meetingId, true, true),
    enabled: !!meetingId,
    refetchOnWindowFocus: false,
  });
}
