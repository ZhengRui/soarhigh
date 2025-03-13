import { useQuery } from '@tanstack/react-query';
import { CategoryCandidatesIF } from '@/interfaces';
import { getVotes } from '@/utils/votes';

/**
 * Hook to fetch vote form data for a meeting
 * @param meetingId The meeting ID
 * @param addMissingCategories Whether to add missing categories to the vote form data
 * @returns Query result with vote form data (categories and candidates)
 */
export function useVoteForm(
  meetingId: string,
  addMissingCategories: boolean = true
) {
  return useQuery<CategoryCandidatesIF[]>({
    queryKey: ['voteForm', meetingId],
    queryFn: () => getVotes(meetingId, addMissingCategories),
    enabled: !!meetingId,
    refetchOnWindowFocus: false,
  });
}
