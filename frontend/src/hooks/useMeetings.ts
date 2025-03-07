import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getMeetings } from '@/utils/meeting';
import { PaginatedMeetings } from '@/interfaces';

export interface UseMeetingsOptions {
  page?: number;
  pageSize?: number;
  status?: string;
}

/**
 * Hook to fetch meetings with pagination
 * @param options Pagination and filter options
 * @returns Query result with paginated meetings data
 */
export function useMeetings(options: UseMeetingsOptions = {}) {
  const { page = 1, pageSize = 10, status } = options;

  const query = useQuery<PaginatedMeetings>({
    queryKey: ['meetings', { page, pageSize, status }],
    queryFn: () =>
      getMeetings({
        page,
        pageSize,
        status,
      }),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000, // 1 minute
  });

  // Return the query result with an added flag for background refreshes
  return {
    ...query,
    // Utility flag to tell if we're showing data while refreshing in background
    isRefreshingInBackground: query.isFetching && !query.isPending,
  };
}
