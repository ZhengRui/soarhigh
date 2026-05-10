import { useCallback, useRef } from 'react';
import { AgentTurnEvent } from './types';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

export function usePublicAgentTurn({
  onEvent,
}: {
  onEvent: (ev: AgentTurnEvent) => void;
}) {
  const controllerRef = useRef<AbortController | null>(null);

  const reportError = useCallback(
    (message: string, recoverable = true) => {
      onEvent({
        type: 'error',
        data: { reason: 'transport_error', recoverable, message },
      });
    },
    [onEvent]
  );

  const ensureVisitor = useCallback(async () => {
    const res = await fetch(`${apiEndpoint}/agent-public/visitor`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) {
      throw new Error(`Visitor setup returned ${res.status}`);
    }
  }, []);

  const send = useCallback(
    async (args: { session_id: string; user_message: string }) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      let res: Response;
      try {
        await ensureVisitor();
        const token =
          typeof window !== 'undefined' ? localStorage.getItem('token') : null;
        res = await fetch(`${apiEndpoint}/agent-public/turn`, {
          method: 'POST',
          headers: {
            Accept: 'text/event-stream',
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          credentials: 'include',
          body: JSON.stringify({
            session_id: args.session_id,
            user_message: args.user_message,
          }),
          signal: controller.signal,
        });
      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          onEvent({ type: 'cancelled', data: {} });
          return;
        }
        reportError((e as Error).message || 'Network error');
        return;
      }

      if (!res.ok || !res.body) {
        reportError(`Server returned ${res.status}`, res.status !== 403);
        return;
      }

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
          reportError((e as Error).message || 'Stream read error');
        }
      }
    },
    [ensureVisitor, onEvent, reportError]
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  return { send, stop };
}
