import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getPosts } from '@/utils/posts';
import { PaginatedPosts } from '@/interfaces';

export interface UsePostsOptions {
  page?: number;
  pageSize?: number;
}

/**
 * Hook to fetch posts with pagination
 * @param options Pagination and filter options
 * @returns Query result with paginated posts data
 */
export function usePosts(options: UsePostsOptions = {}) {
  const { page = 1, pageSize = 10 } = options;

  const query = useQuery<PaginatedPosts>({
    queryKey: ['posts', { page, pageSize }],
    queryFn: () => getPosts({ page, pageSize }),
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
