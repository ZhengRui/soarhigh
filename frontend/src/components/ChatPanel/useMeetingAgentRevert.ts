import { useCallback } from 'react';
import { AgendaSnapshot } from './types';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

export type RevertResponse = {
  agenda: AgendaSnapshot;
  new_tail_seq: number;
};

export function useMeetingAgentRevert() {
  return useCallback(
    async (sessionId: string, targetSeq: number): Promise<RevertResponse> => {
      const token =
        typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const res = await fetch(`${apiEndpoint}/meeting-agent/revert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          session_id: sessionId,
          target_seq: targetSeq,
        }),
      });
      if (!res.ok) {
        throw new Error(`revert failed: ${res.status}`);
      }
      return (await res.json()) as RevertResponse;
    },
    []
  );
}
