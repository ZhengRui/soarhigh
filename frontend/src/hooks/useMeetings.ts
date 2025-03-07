import { useAtom } from 'jotai';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getMeetings } from '@/utils/meeting';
import { PaginatedMeetings } from '@/interfaces';
import { meetingsAtom } from '@/atoms';
import { useEffect } from 'react';

export interface UseMeetingsOptions {
  page?: number;
  pageSize?: number;
  status?: string;
}

/**
 * Hook to fetch meetings with pagination and store in global Jotai state
 * @param options Pagination and filter options
 * @returns Query result with paginated meetings data
 */
export function useMeetings(options: UseMeetingsOptions = {}) {
  const { page = 1, pageSize = 10, status } = options;
  const [meetingsState, setMeetingsState] = useAtom(meetingsAtom);

  // Get cached data for this page if available
  const cachedData = meetingsState.pages[page];
  const hasCache = !!cachedData;

  // Standard React Query to fetch data
  const query = useQuery<PaginatedMeetings>({
    queryKey: ['meetings', { page, pageSize, status }],
    queryFn: () =>
      getMeetings({
        page,
        pageSize,
        status,
      }),
    placeholderData: keepPreviousData,
    // If we have cache, we can increase staleTime to prevent immediate refetch
    staleTime: hasCache ? 30000 : 0,
  });

  // Use useEffect as an alternative to onSuccess to update Jotai store when query succeeds
  useEffect(() => {
    if (query.data && !query.isPending && !query.isError) {
      setMeetingsState((prev) => ({
        ...prev,
        pages: {
          ...prev.pages,
          [page]: query.data,
        },
      }));
    }
  }, [query.data, query.isPending, query.isError, page, setMeetingsState]);

  // Determine what data to return - prefer cached data during loading
  const effectiveData =
    (query.isPending || query.isFetching) && hasCache ? cachedData : query.data;

  // Return both the effective data for UI rendering and the query object for status
  return {
    ...query,
    data: effectiveData,
    // Utility flag to tell if we're showing cached data while refreshing
    isRefreshingInBackground: query.isFetching && hasCache,
  };
}
