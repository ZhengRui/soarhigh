import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveMeetingAwards } from '@/utils/meeting';
import { AwardIF } from '@/interfaces';

interface SaveAwardsData {
  meetingId: string;
  awards: AwardIF[];
}

/**
 * Hook for saving meeting awards
 * @returns Mutation for saving meeting awards
 */
export function useSaveMeetingAwards() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ meetingId, awards }: SaveAwardsData) =>
      saveMeetingAwards(meetingId, awards),
    onSuccess: (_, data) => {
      // Invalidate meetings queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['meetings'] });
      queryClient.invalidateQueries({
        queryKey: ['meeting', data.meetingId],
      });
    },
  });
}
