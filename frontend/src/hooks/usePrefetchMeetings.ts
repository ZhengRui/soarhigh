import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { getMeetings } from '@/utils/meeting';

/**
 * Hook to prefetch adjacent pages for meetings pagination
 * @param currentPage Current page number
 * @param totalPages Total number of pages
 * @param pageSize Page size
 * @param status Optional status filter
 */
export function usePrefetchMeetings(
  currentPage: number,
  totalPages: number,
  pageSize: number = 10,
  status?: string
) {
  const queryClient = useQueryClient();

  useEffect(() => {
    // Only prefetch if we have pagination data
    if (!totalPages) return;

    // Prefetch next page if not the last page
    if (currentPage < totalPages) {
      queryClient.prefetchQuery({
        queryKey: ['meetings', { page: currentPage + 1, pageSize, status }],
        queryFn: () =>
          getMeetings({
            page: currentPage + 1,
            pageSize,
            status,
          }),
      });
    }

    // Prefetch previous page if not the first page
    if (currentPage > 1) {
      queryClient.prefetchQuery({
        queryKey: ['meetings', { page: currentPage - 1, pageSize, status }],
        queryFn: () =>
          getMeetings({
            page: currentPage - 1,
            pageSize,
            status,
          }),
      });
    }
  }, [currentPage, totalPages, pageSize, status, queryClient]);
}
