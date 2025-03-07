'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Create a client with improved caching configuration
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Increase staleTime to reduce unnecessary refetches
      staleTime: 60 * 1000, // 1 minute
      // Keep cache alive longer
      gcTime: 10 * 60 * 1000, // 10 minutes
      // Prevent refetch on window focus for better UX
      refetchOnWindowFocus: false,
      // Retry failed queries fewer times
      retry: 1,
    },
  },
});

export default function QueryProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
