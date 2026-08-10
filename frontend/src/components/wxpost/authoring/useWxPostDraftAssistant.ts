'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import {
  getWorkspaceContext,
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

function isRecoverableStreamFailure(error: unknown) {
  return (
    error instanceof TypeError ||
    (error instanceof WorkspaceApiError &&
      (error.code === 'incomplete_stream' || error.code === 'invalid_stream'))
  );
}

const DRAFT_RECOVERY_TIMEOUT_MS = 90_000;
const DRAFT_RECOVERY_POLL_MS = 1_000;

function waitForRecoveryPoll(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(signal.reason);
    };
    const timeout = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, DRAFT_RECOVERY_POLL_MS);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

async function waitForRecoveredDraftContext(
  workspaceId: string,
  expectedDraftVersion: number,
  signal: AbortSignal
) {
  const deadline = Date.now() + DRAFT_RECOVERY_TIMEOUT_MS;
  let context = await getWorkspaceContext(workspaceId);
  while (
    (context.draft?.draftVersion ?? 0) === expectedDraftVersion &&
    Date.now() < deadline
  ) {
    await waitForRecoveryPoll(signal);
    context = await getWorkspaceContext(workspaceId);
  }
  return context;
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
    const previousMessageCount = session?.messages.length ?? 0;
    const expectedDraftVersion = savedDraft.draftVersion;
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
      const finishedSteps = progressRef.current.filter(
        (step) => step.completed || step.failed
      );
      setSession((current) => ({
        workspaceId,
        sessionId: result.sessionId,
        messages: [
          ...(current?.messages ?? []),
          {
            role: 'assistant',
            text: result.reply,
            ...(finishedSteps.length > 0 ? { steps: finishedSteps } : {}),
          },
        ],
      }));
    } catch (caught) {
      if (isRecoverableStreamFailure(caught)) {
        try {
          // The Controller deliberately finishes a Draft turn after a browser
          // disconnect. Context reads do not take the per-workspace turn lock,
          // so poll the saved Draft first instead of blocking recovery on
          // session history while the disconnected turn is still running.
          const recoveryActivity: DraftProgressActivity = {
            activityId: 'recover-disconnected-turn',
            label: 'Finishing the Draft update in the background',
            completed: false,
            failed: false,
          };
          progressRef.current = [
            ...progressRef.current.filter(
              (item) => item.activityId !== recoveryActivity.activityId
            ),
            recoveryActivity,
          ];
          setProgress(progressRef.current);
          const context = await waitForRecoveredDraftContext(
            workspaceId,
            expectedDraftVersion,
            requestController.signal
          );
          const history = await getWorkspaceDraftSession(workspaceId);
          const completedTurn = history.messages.slice(previousMessageCount);
          const recoveredUser = completedTurn[0];
          const recoveredAssistant = completedTurn[1];
          const actualDraftVersion = context.draft?.draftVersion ?? 0;
          const draftChanged = actualDraftVersion === expectedDraftVersion + 1;
          if (
            recoveredUser?.role === 'user' &&
            recoveredUser.text === request &&
            recoveredAssistant?.role === 'assistant' &&
            (actualDraftVersion === expectedDraftVersion || draftChanged)
          ) {
            setStatus('online');
            setSession(history);
            if (draftChanged) {
              try {
                await onDraftChanged(context);
              } catch (recoveryError) {
                const failure = errorMessage(
                  recoveryError,
                  'The Draft was saved, but the updated preview could not be loaded.'
                );
                onError(failure);
                toast.error(failure);
              }
            }
            return;
          }
        } catch {
          // Preserve the original transport error when reconciliation cannot
          // prove that this exact turn completed.
        }
      }
      setMessage(request);
      setSession((current) =>
        current
          ? { ...current, messages: current.messages.slice(0, -1) }
          : current
      );
      if (
        caught instanceof WorkspaceApiError &&
        caught.code === 'version_conflict' &&
        caught.versionKind === 'draft'
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
    session,
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
