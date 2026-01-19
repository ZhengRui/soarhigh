import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getDashboardStats } from '@/utils/stats';
import { DashboardStatsIF } from '@/interfaces';

export interface UseDashboardOptions {
  startDate: string;
  endDate: string;
}

/**
 * Hook to fetch dashboard statistics for a date range
 * @param options Date range options (startDate, endDate in YYYY-MM-DD format)
 * @returns Query result with dashboard stats
 */
export function useDashboardStats(options: UseDashboardOptions) {
  const { startDate, endDate } = options;

  const query = useQuery<DashboardStatsIF>({
    queryKey: ['dashboardStats', startDate, endDate],
    queryFn: () => getDashboardStats(startDate, endDate),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: !!startDate && !!endDate,
  });

  return {
    ...query,
    isRefreshingInBackground: query.isFetching && !query.isPending,
  };
}
