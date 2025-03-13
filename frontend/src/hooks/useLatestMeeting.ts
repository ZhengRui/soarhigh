import { useQuery } from '@tanstack/react-query';
import { MeetingIF } from '@/interfaces';
import { getMeetings } from '@/utils/meeting';

/**
 * Hook to fetch the latest meeting
 * @returns Query result with the latest meeting data
 */
export function useLatestMeeting() {
  return useQuery<MeetingIF>({
    queryKey: ['latestMeeting'],
    queryFn: async () => {
      // Fetch the latest meeting (first in the list, sorted by date/no)
      const result = await getMeetings({
        page: 1,
        pageSize: 1,
      });

      // Return the first meeting or null if no meetings
      return result.items[0] || null;
    },
    staleTime: 60 * 1000, // 1 minute
  });
}
