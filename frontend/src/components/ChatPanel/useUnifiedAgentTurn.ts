import { useCallback, useRef } from 'react';
import { AgendaSnapshot, AgentTurnEvent } from './types';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

export function useUnifiedAgentTurn({
  onEvent,
}: {
  onEvent: (ev: AgentTurnEvent) => void;
}) {
  const controllerRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (args: {
      session_id: string;
      user_message: string;
      agenda_snapshot: AgendaSnapshot;
      image?: File | null;
    }) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      const token =
        typeof window !== 'undefined' ? localStorage.getItem('token') : null;

      // The unified route accepts multipart so the create-from-image flow can
      // attach an image alongside the JSON payload. No-image turns just have
      // an empty `image` field.
      const form = new FormData();
      form.append(
        'payload',
        JSON.stringify({
          session_id: args.session_id,
          user_message: args.user_message,
          agenda_snapshot: args.agenda_snapshot,
        })
      );
      if (args.image) form.append('image', args.image, args.image.name);

      // Synthesize an error event into onEvent so the chat panel's
      // existing handler shows the banner + clears loading. Without
      // this, fetch failures or non-OK responses would propagate to
      // the caller's catch and leave a stuck empty "…" bubble.
      const reportError = (message: string) => {
        onEvent({
          type: 'error',
          data: { reason: 'transport_error', recoverable: true, message },
        });
      };

      let res: Response;
      try {
        res = await fetch(`${apiEndpoint}/agent/turn`, {
          method: 'POST',
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: form,
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
        reportError(`Server returned ${res.status}`);
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
    [onEvent]
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  return { send, stop };
}
