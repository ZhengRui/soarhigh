import { useInfiniteQuery } from '@tanstack/react-query';
import type { PaginatedMeetingOptions } from '@/interfaces';
import { getMeetingOptions } from '@/utils/meeting';

interface UseMeetingOptionsListOptions {
  pageSize?: number;
  status?: string;
}

export function useMeetingOptions(options: UseMeetingOptionsListOptions = {}) {
  const { pageSize = 50, status } = options;

  return useInfiniteQuery<PaginatedMeetingOptions>({
    queryKey: ['meeting-options', { pageSize, status }],
    queryFn: ({ pageParam }) =>
      getMeetingOptions({
        page: Number(pageParam),
        pageSize,
        status,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page < lastPage.pages ? lastPage.page + 1 : undefined,
    staleTime: 60 * 1000,
  });
}
