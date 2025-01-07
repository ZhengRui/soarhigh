import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getMembers } from '@/utils/auth';
import { UserIF } from '@/interfaces';

export const useMembers = () => {
  return useQuery<UserIF[]>({
    queryKey: ['members'],
    queryFn: getMembers,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
};
