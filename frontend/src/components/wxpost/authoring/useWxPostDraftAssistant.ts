'use client';

import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';

import {
  getWorkspaceDraftSession,
  reviseWorkspaceDraft,
  WorkspaceApiError,
  type WorkspaceContext,
  type WorkspaceDraftSession,
} from '@/utils/wxpostWorkspace';

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function useWxPostDraftAssistant({
  active,
  workspaceId,
  manifestVersion,
  savedDraft,
  dirty,
  selectedText,
  onContextChange,
  onDraftAccepted,
  onConflict,
  onError,
}: {
  active: boolean;
  workspaceId: string;
  manifestVersion: number;
  savedDraft: WorkspaceContext['draft'];
  dirty: boolean;
  selectedText: string | null;
  onContextChange: (context: WorkspaceContext) => void;
  onDraftAccepted: () => void;
  onConflict: () => void;
  onError: (message: string | null) => void;
}) {
  const [session, setSession] = useState<WorkspaceDraftSession | null>(null);
  const [status, setStatus] = useState<'connecting' | 'online' | 'unavailable'>(
    'connecting'
  );
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!active || session) return;
    void getWorkspaceDraftSession(workspaceId)
      .then((history) => {
        setSession(history);
        setStatus('online');
      })
      .catch(() => {
        setSession({ workspaceId, sessionId: null, messages: [] });
        setStatus('unavailable');
      });
  }, [active, session, workspaceId]);

  const send = useCallback(async () => {
    const request = message.trim();
    if (!request || !savedDraft || dirty) return;
    setPending(true);
    onError(null);
    setSession((current) => ({
      workspaceId,
      sessionId: current?.sessionId ?? null,
      messages: [...(current?.messages ?? []), { role: 'user', text: request }],
    }));
    setMessage('');
    try {
      const result = await reviseWorkspaceDraft(workspaceId, {
        expectedManifestVersion: manifestVersion,
        expectedDraftVersion: savedDraft.draftVersion,
        message: request,
        selectedText,
      });
      onContextChange(result.context);
      setStatus('online');
      onDraftAccepted();
      setSession((current) => ({
        workspaceId,
        sessionId: result.sessionId,
        messages: [
          ...(current?.messages ?? []),
          { role: 'assistant', text: result.reply },
        ],
      }));
    } catch (caught) {
      setMessage(request);
      setSession((current) =>
        current
          ? { ...current, messages: current.messages.slice(0, -1) }
          : current
      );
      if (
        caught instanceof WorkspaceApiError &&
        caught.code === 'version_conflict'
      ) {
        onConflict();
        return;
      }
      if (
        caught instanceof WorkspaceApiError &&
        ['hermes_unavailable', 'hermes_turn_failed'].includes(caught.code ?? '')
      ) {
        setStatus('unavailable');
      }
      const failure = errorMessage(
        caught,
        'Hermes could not revise the draft.'
      );
      onError(failure);
      toast.error(failure);
    } finally {
      setPending(false);
    }
  }, [
    dirty,
    manifestVersion,
    message,
    onConflict,
    onContextChange,
    onDraftAccepted,
    onError,
    savedDraft,
    selectedText,
    workspaceId,
  ]);

  return {
    session,
    status,
    message,
    pending,
    setMessage,
    send,
  };
}
