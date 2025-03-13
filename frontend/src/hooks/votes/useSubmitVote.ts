import { useMutation, useQueryClient } from '@tanstack/react-query';
import { castVotes } from '@/utils/votes';
import { VoteRecordIF } from '@/interfaces';

/**
 * Hook to submit votes for a meeting
 * @returns Mutation object for submitting votes
 */
export function useSubmitVote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      meetingId,
      votes,
    }: {
      meetingId: string;
      votes: VoteRecordIF[];
    }) => {
      return castVotes(meetingId, votes);
    },
    onSuccess: (_, variables) => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({
        queryKey: ['voteForm', variables.meetingId],
      });
    },
  });
}
