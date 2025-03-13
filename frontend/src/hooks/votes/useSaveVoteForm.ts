import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { CategoryCandidatesIF } from '@/interfaces';
import { saveVoteForm } from '@/utils/votes';

interface SaveVoteFormParams {
  meetingId: string;
  voteForm: CategoryCandidatesIF[];
}

/**
 * Hook for saving vote form data
 * @returns Mutation for saving vote form
 */
export function useSaveVoteForm() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ meetingId, voteForm }: SaveVoteFormParams) =>
      saveVoteForm(meetingId, voteForm),
    onSuccess: (_, { meetingId }) => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['voteForm', meetingId] });
      toast.success('Vote form saved successfully');
    },
    onError: (error) => {
      console.error('Error saving vote form:', error);
      toast.error('Failed to save vote form');
    },
  });
}
