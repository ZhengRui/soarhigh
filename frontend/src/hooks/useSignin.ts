import { useMutation, useQueryClient } from '@tanstack/react-query';
import { signin } from '@/utils/auth';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';

export const useSigninMutation = () => {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: ({
      username,
      password,
    }: {
      username: string;
      password: string;
    }) => signin(username, password),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['whoami'] });
      router.push('/');
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : (err as string));
    },
  });
};
