import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getPost } from '@/utils/posts';
import { PostIF } from '@/interfaces';

export function usePost(slug: string) {
  return useQuery<PostIF>({
    queryKey: ['post', slug],
    queryFn: () => {
      if (!slug) throw new Error('Slug is required');
      return getPost(slug);
    },
    enabled: !!slug,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}
