import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { getMeetings } from '@/utils/meeting';
import { useAtom } from 'jotai';
import { meetingsAtom } from '@/atoms';
import { PaginatedMeetings } from '@/interfaces';

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
  const [meetingsState, setMeetingsState] = useAtom(meetingsAtom);

  useEffect(() => {
    // Only prefetch if we have pagination data
    if (!totalPages) return;

    // Helper function to prefetch a page and update Jotai store
    const prefetchPage = async (page: number) => {
      // Check if we already have this page cached in Jotai store
      if (meetingsState.pages[page]) return;

      try {
        // Prefetch the data
        await queryClient.prefetchQuery({
          queryKey: ['meetings', { page, pageSize, status }],
          queryFn: () =>
            getMeetings({
              page,
              pageSize,
              status,
            }),
        });

        // After prefetching, manually check the cache for the data
        const cachedData = queryClient.getQueryData<PaginatedMeetings>([
          'meetings',
          { page, pageSize, status },
        ]);

        // If we have data in the cache, update Jotai store
        if (cachedData) {
          setMeetingsState((prev) => ({
            ...prev,
            pages: {
              ...prev.pages,
              [page]: cachedData,
            },
          }));
        }
      } catch (error) {
        console.error(`Error prefetching page ${page}:`, error);
      }
    };

    // Prefetch next page if not the last page
    if (currentPage < totalPages) {
      prefetchPage(currentPage + 1);
    }

    // Prefetch previous page if not the first page
    if (currentPage > 1) {
      prefetchPage(currentPage - 1);
    }
  }, [
    currentPage,
    totalPages,
    pageSize,
    status,
    queryClient,
    meetingsState.pages,
    setMeetingsState,
  ]);
}
