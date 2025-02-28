import { useQuery } from '@tanstack/react-query';
import { getMeetingById } from '@/utils/meeting';
import { MeetingIF } from '@/interfaces';

/**
 * Hook to fetch a meeting by ID
 * @param id The meeting ID to fetch
 * @returns Query result with meeting data
 */
export function useMeeting(id?: string) {
  return useQuery<MeetingIF>({
    queryKey: ['meeting', id],
    queryFn: () => {
      if (!id) throw new Error('Meeting ID is required');
      return getMeetingById(id);
    },
    enabled: !!id, // Only run the query if we have an ID
  });
}
