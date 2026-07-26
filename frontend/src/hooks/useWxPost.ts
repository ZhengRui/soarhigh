import { useQuery } from '@tanstack/react-query';

import type { WxPostPublicDetail } from '@/components/wxpost/types';
import { getWxPost } from '@/utils/wxposts';

export function useWxPost(slug: string) {
  return useQuery<WxPostPublicDetail>({
    queryKey: ['wxpost', slug],
    queryFn: () => getWxPost(slug),
    enabled: Boolean(slug),
    refetchOnWindowFocus: false,
  });
}
