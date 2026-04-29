import { useCallback, useRef } from 'react';
import { AgentTurnEvent } from './types';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * SSE stream client for the statistics agent.
 *
 * Mirrors useMeetingAgentTurn's wire shape — same SSE event names
 * (assistant_text, thinking, tool_call_start, tool_call_end, done,
 * error) — but posts JSON instead of multipart since the stats agent
 * doesn't accept image attachments and has no agenda payload.
 */
export function useStatisticsAgentTurn({
  onEvent,
}: {
  onEvent: (ev: AgentTurnEvent) => void;
}) {
  const controllerRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (args: { session_id: string; user_message: string }) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      const token =
        typeof window !== 'undefined' ? localStorage.getItem('token') : null;

      const res = await fetch(`${apiEndpoint}/statistics-agent/turn`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          session_id: args.session_id,
          user_message: args.user_message,
        }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`Bad response: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let nl;
          while ((nl = buf.indexOf('\n\n')) !== -1) {
            const raw = buf.slice(0, nl);
            buf = buf.slice(nl + 2);
            const lines = raw.split('\n');
            let event: string | null = null;
            let data: unknown = null;
            for (const line of lines) {
              if (line.startsWith('event: ')) event = line.slice(7);
              if (line.startsWith('data: ')) data = JSON.parse(line.slice(6));
            }
            if (event) onEvent({ type: event, data } as AgentTurnEvent);
          }
        }
      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          onEvent({ type: 'cancelled', data: {} });
        } else {
          throw e;
        }
      }
    },
    [onEvent]
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  return { send, stop };
}
