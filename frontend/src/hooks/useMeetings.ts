import { useQuery } from '@tanstack/react-query';
import { getMeetings } from '@/utils/meeting';
import { MeetingIF } from '@/interfaces';

/**
 * Hook to fetch all meetings
 * @returns Query result with meetings data
 */
export function useMeetings() {
  return useQuery<MeetingIF[]>({
    queryKey: ['meetings'],
    queryFn: () => getMeetings(),
  });
}
