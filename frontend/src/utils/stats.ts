import { DashboardStatsIF } from '../interfaces';
import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * Fetches dashboard statistics for a given date range
 * @param startDate Start date in YYYY-MM-DD format
 * @param endDate End date in YYYY-MM-DD format
 * @returns Dashboard stats containing member meetings and meeting attendance data
 */
export const getDashboardStats = requestTemplate(
  (startDate: string, endDate: string) => ({
    url: `${apiEndpoint}/stats/dashboard?start_date=${startDate}&end_date=${endDate}`,
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  true, // Requires authentication
  false // Not soft auth - must be logged in
) as (startDate: string, endDate: string) => Promise<DashboardStatsIF>;
