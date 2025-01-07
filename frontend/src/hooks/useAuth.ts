import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { whoami } from '@/utils/auth';
import { UserIF } from '@/interfaces';

export const useAuth = () =>
  useQuery<UserIF>({
    queryKey: ['whoami'],
    queryFn: () => whoami(),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
