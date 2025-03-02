import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { isAdmin } from '@/utils/auth';

export const useIsAdmin = () =>
  useQuery<boolean>({
    queryKey: ['isAdmin'],
    queryFn: isAdmin,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
