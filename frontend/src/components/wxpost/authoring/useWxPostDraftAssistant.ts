'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import {
  draftAssistantErrorStatus,
  getWorkspaceContext,
  getWorkspaceDraftOperation,
  getWorkspaceDraftConversation,
  chatWithWorkspaceDraft,
  resetWorkspaceDraftConversation,
  WorkspaceApiError,
  type WorkspaceContext,
  type WorkspaceDraftProgressActivity,
  type WorkspaceDraftConversation,
} from '@/utils/wxpostWorkspace';

export type DraftProgressActivity = WorkspaceDraftProgressActivity;
export type DraftAssistantStatus = 'connecting' | 'ready' | 'unavailable';

function isAssistantUnavailable(error: unknown) {
  return (
    error instanceof WorkspaceApiError &&
    draftAssistantErrorStatus(error.code) === 503
  );
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function isRecoverableStreamFailure(error: unknown) {
  return (
    error instanceof TypeError ||
    (error instanceof WorkspaceApiError &&
      (error.code === 'incomplete_stream' ||
        error.code === 'invalid_stream' ||
        (error.code === null && [502, 503, 504].includes(error.status))))
  );
}

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

async function waitForDraftOperation(
  workspaceId: string,
  operationId: string,
  signal: AbortSignal
) {
  let operation = await getWorkspaceDraftOperation(
    workspaceId,
    operationId,
    signal
  );
  while (operation.state === 'running') {
    await waitForRecoveryPoll(signal);
    operation = await getWorkspaceDraftOperation(
      workspaceId,
      operationId,
      signal
    );
  }
  if (operation.state === 'failed') {
    const errorCode = operation.error?.code ?? 'operation_failed';
    throw new WorkspaceApiError(
      draftAssistantErrorStatus(errorCode),
      operation.error?.message ??
        'The Draft Assistant could not complete the request.',
      errorCode,
      operation.error?.versionKind ?? null
    );
  }
  if (!operation.result) {
    throw new WorkspaceApiError(
      502,
      'The Draft Assistant returned an invalid operation result.',
      'invalid_operation'
    );
  }
  return operation.result;
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
  const [conversation, setConversation] =
    useState<WorkspaceDraftConversation | null>(null);
  const [status, setStatus] = useState<DraftAssistantStatus>('connecting');
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
    if (!active || conversation) return;
    const requestId = ++historyRequestIdRef.current;
    void getWorkspaceDraftConversation(workspaceId)
      .then((history) => {
        if (historyRequestIdRef.current !== requestId) return;
        setConversation(history);
        setStatus('ready');
      })
      .catch(() => {
        if (historyRequestIdRef.current !== requestId) return;
        setConversation({ workspaceId, messages: [] });
        setStatus('unavailable');
      });
    return () => {
      if (historyRequestIdRef.current === requestId) {
        historyRequestIdRef.current += 1;
      }
    };
  }, [active, conversation, workspaceId]);

  const send = useCallback(async () => {
    const request = message.trim();
    if (!request || !savedDraft || dirty) return;
    const requestController = new AbortController();
    const operationId = `draft-${crypto.randomUUID().replaceAll('-', '')}`;
    requestControllerRef.current = requestController;
    setPending(true);
    setProgress([]);
    progressRef.current = [];
    onError(null);
    setConversation((current) => ({
      workspaceId,
      messages: [
        ...(current?.messages ?? []),
        {
          role: 'user',
          text: request,
          ...(selectedText ? { selectedText } : {}),
        },
      ],
    }));
    setMessage('');
    try {
      const result = await chatWithWorkspaceDraft(
        workspaceId,
        {
          expectedManifestVersion: manifestVersion,
          expectedDraftVersion: savedDraft.draftVersion,
          operationId,
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
      setStatus('ready');
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
      setConversation((current) => ({
        workspaceId,
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
      let failureCause = caught;
      if (isRecoverableStreamFailure(caught)) {
        try {
          // The Controller deliberately finishes a Draft turn after a browser
          // disconnect. Its durable operation record is independent of the
          // workspace turn and file locks, so it remains readable while the
          // disconnected turn is still running.
          const recoveryActivity: DraftProgressActivity = {
            activityId: 'recover-disconnected-turn',
            label: 'Reconnecting to the Draft operation',
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
          const recovered = await waitForDraftOperation(
            workspaceId,
            operationId,
            requestController.signal
          );
          const context = await getWorkspaceContext(
            workspaceId,
            requestController.signal
          );
          const actualDraftVersion = context.draft?.draftVersion ?? 0;
          if (actualDraftVersion !== recovered.draftVersion) {
            throw new WorkspaceApiError(
              409,
              'The saved Draft changed again before recovery completed.',
              'version_conflict',
              'draft'
            );
          }
          setStatus('ready');
          setConversation((current) => ({
            workspaceId,
            messages: [
              ...(current?.messages ?? []),
              {
                role: 'assistant',
                text: recovered.reply,
                turnId: operationId,
                steps: recovered.steps,
              },
            ],
          }));
          if (recovered.draftChanged) {
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
        } catch (recoveryError) {
          if (
            !(
              recoveryError instanceof WorkspaceApiError &&
              recoveryError.code === 'draft_operation_not_found'
            )
          ) {
            failureCause = recoveryError;
          }
        }
      }
      setMessage(request);
      setConversation((current) =>
        current
          ? { ...current, messages: current.messages.slice(0, -1) }
          : current
      );
      if (
        failureCause instanceof WorkspaceApiError &&
        failureCause.code === 'version_conflict' &&
        failureCause.versionKind === 'draft'
      ) {
        onConflict();
        return;
      }
      if (isAssistantUnavailable(failureCause)) {
        setStatus('unavailable');
      }
      const failure = errorMessage(
        failureCause,
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
      const nextConversation =
        await resetWorkspaceDraftConversation(workspaceId);
      setConversation(nextConversation);
      setMessage('');
      setProgress([]);
      progressRef.current = [];
      setStatus('ready');
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
    conversation,
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
