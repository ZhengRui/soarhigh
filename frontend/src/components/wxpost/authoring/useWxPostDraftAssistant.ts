'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import {
  getWorkspaceDraftSession,
  chatWithWorkspaceDraft,
  resetWorkspaceDraftSession,
  WorkspaceApiError,
  type WorkspaceContext,
  type WorkspaceDraftProgressActivity,
  type WorkspaceDraftSession,
} from '@/utils/wxpostWorkspace';

export type DraftProgressActivity = WorkspaceDraftProgressActivity;

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
  onDraftChanged,
  onConflict,
  onError,
}: {
  active: boolean;
  workspaceId: string;
  manifestVersion: number;
  savedDraft: WorkspaceContext['draft'];
  dirty: boolean;
  selectedText: string | null;
  onDraftChanged: (context: WorkspaceContext) => Promise<void>;
  onConflict: () => void;
  onError: (message: string | null) => void;
}) {
  const [session, setSession] = useState<WorkspaceDraftSession | null>(null);
  const [status, setStatus] = useState<'connecting' | 'online' | 'unavailable'>(
    'connecting'
  );
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);
  const [resetPending, setResetPending] = useState(false);
  const [progress, setProgress] = useState<DraftProgressActivity[]>([]);
  const progressRef = useRef<DraftProgressActivity[]>([]);
  const requestControllerRef = useRef<AbortController | null>(null);
  const historyRequestIdRef = useRef(0);

  useEffect(
    () => () => {
      requestControllerRef.current?.abort();
    },
    []
  );

  useEffect(() => {
    if (!active || session) return;
    const requestId = ++historyRequestIdRef.current;
    void getWorkspaceDraftSession(workspaceId)
      .then((history) => {
        if (historyRequestIdRef.current !== requestId) return;
        setSession(history);
        setStatus('online');
      })
      .catch(() => {
        if (historyRequestIdRef.current !== requestId) return;
        setSession({ workspaceId, sessionId: null, messages: [] });
        setStatus('unavailable');
      });
    return () => {
      if (historyRequestIdRef.current === requestId) {
        historyRequestIdRef.current += 1;
      }
    };
  }, [active, session, workspaceId]);

  const send = useCallback(async () => {
    const request = message.trim();
    if (!request || !savedDraft || dirty) return;
    const requestController = new AbortController();
    requestControllerRef.current = requestController;
    setPending(true);
    setProgress([]);
    progressRef.current = [];
    onError(null);
    setSession((current) => ({
      workspaceId,
      sessionId: current?.sessionId ?? null,
      messages: [...(current?.messages ?? []), { role: 'user', text: request }],
    }));
    setMessage('');
    try {
      const result = await chatWithWorkspaceDraft(
        workspaceId,
        {
          expectedManifestVersion: manifestVersion,
          expectedDraftVersion: savedDraft.draftVersion,
          message: request,
          selectedText,
        },
        {
          signal: requestController.signal,
          onProgress: (next) => {
            if (next.stage === 'request_started') {
              return;
            }
            const activityId = next.activityId;
            const label = next.label;
            if (!activityId || !label) return;
            const existingIndex = progressRef.current.findIndex(
              (item) => item.activityId === activityId
            );
            if (existingIndex < 0) {
              progressRef.current = [
                ...progressRef.current,
                {
                  activityId,
                  label,
                  toolName: next.toolName,
                  operationNames: next.operationNames,
                  completed: next.stage === 'activity_completed',
                  failed: next.stage === 'activity_failed',
                },
              ];
            } else {
              progressRef.current = progressRef.current.map((item, index) =>
                index === existingIndex
                  ? {
                      ...item,
                      label,
                      toolName: next.toolName ?? item.toolName,
                      operationNames:
                        next.operationNames ?? item.operationNames,
                      completed: next.stage === 'activity_completed',
                      failed: next.stage === 'activity_failed',
                    }
                  : item
              );
            }
            setProgress(progressRef.current);
          },
        }
      );
      setStatus('online');
      if (result.draftChanged) {
        try {
          await onDraftChanged(result.context);
        } catch (caught) {
          const failure = errorMessage(
            caught,
            'The Draft was saved, but the updated preview could not be loaded.'
          );
          onError(failure);
          toast.error(failure);
        }
      }
      const completedSteps = progressRef.current.filter(
        (step) => step.completed
      );
      setSession((current) => ({
        workspaceId,
        sessionId: result.sessionId,
        messages: [
          ...(current?.messages ?? []),
          {
            role: 'assistant',
            text: result.reply,
            ...(completedSteps.length > 0 ? { steps: completedSteps } : {}),
          },
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
        caught.code === 'hermes_unavailable'
      ) {
        setStatus('unavailable');
      }
      const failure = errorMessage(
        caught,
        'The Draft Assistant could not complete the request.'
      );
      onError(failure);
      toast.error(failure);
    } finally {
      if (requestControllerRef.current === requestController) {
        requestControllerRef.current = null;
      }
      setProgress([]);
      progressRef.current = [];
      setPending(false);
    }
  }, [
    dirty,
    manifestVersion,
    message,
    onConflict,
    onDraftChanged,
    onError,
    savedDraft,
    selectedText,
    workspaceId,
  ]);

  const reset = useCallback(async () => {
    if (pending || resetPending) return false;
    historyRequestIdRef.current += 1;
    setResetPending(true);
    onError(null);
    try {
      const nextSession = await resetWorkspaceDraftSession(workspaceId);
      setSession(nextSession);
      setMessage('');
      setProgress([]);
      progressRef.current = [];
      setStatus('online');
      toast.success('Started a new Draft Assistant conversation.');
      return true;
    } catch (caught) {
      const failure = errorMessage(
        caught,
        'The Draft Assistant conversation could not be reset.'
      );
      onError(failure);
      toast.error(failure);
      return false;
    } finally {
      setResetPending(false);
    }
  }, [onError, pending, resetPending, workspaceId]);

  return {
    session,
    status,
    message,
    pending,
    resetPending,
    progress,
    setMessage,
    send,
    reset,
  };
}
