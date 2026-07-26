import { useQuery } from '@tanstack/react-query';
import { getPosts } from '@/utils/posts';
import type { ContentKind, PaginatedContentItems } from '@/interfaces';

export interface UsePostsOptions {
  page?: number;
  pageSize?: number;
  kind?: ContentKind;
}

/**
 * Hook to fetch posts with pagination
 * @param options Pagination and filter options
 * @returns Query result with paginated posts data
 */
export function usePosts(options: UsePostsOptions = {}) {
  const { page = 1, pageSize = 10, kind = 'all' } = options;

  const query = useQuery<PaginatedContentItems>({
    queryKey: ['posts', { page, pageSize, kind }],
    queryFn: () => getPosts({ page, pageSize, kind }),
    staleTime: 60 * 1000, // 1 minute
  });

  // Return the query result with an added flag for background refreshes
  return {
    ...query,
    // Utility flag to tell if we're showing data while refreshing in background
    isRefreshingInBackground: query.isFetching && !query.isPending,
  };
}
