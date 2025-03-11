import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { updateVoteStatus } from '@/utils/votes';

interface UpdateVoteStatusParams {
  meetingId: string;
  isOpen: boolean;
}

/**
 * Hook for updating vote status (open/closed)
 * @returns Mutation for updating vote status
 */
export function useUpdateVoteStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ meetingId, isOpen }: UpdateVoteStatusParams) =>
      updateVoteStatus(meetingId, isOpen),
    onSuccess: (data, { meetingId }) => {
      queryClient.invalidateQueries({ queryKey: ['voteStatus', meetingId] });
      toast.success(data.open ? 'Voting is now open' : 'Voting is now closed');
    },
    onError: (error) => {
      console.error('Error updating vote status:', error);
      toast.error('Failed to update voting status');
    },
  });
}
