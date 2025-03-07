import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getMeetings } from '@/utils/meeting';
import { PaginatedMeetings } from '@/interfaces';

interface UseMeetingsOptions {
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

  return useQuery<PaginatedMeetings>({
    queryKey: ['meetings', { page, pageSize, status }],
    queryFn: () =>
      getMeetings({
        page,
        page_size: pageSize,
        status,
      }),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}
