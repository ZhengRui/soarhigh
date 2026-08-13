'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import {
  draftAssistantErrorStatus,
  getWorkspaceContext,
  getWorkspaceDraftOperation,
  getWorkspaceDraftConversation,
  submitWorkspaceDraftChat,
  resetWorkspaceDraftConversation,
  WorkspaceApiError,
  type WorkspaceContext,
  type WorkspaceDraftProgressActivity,
  type WorkspaceDraftConversation,
} from '@/utils/wxpostWorkspace';

export type DraftProgressActivity = WorkspaceDraftProgressActivity;
export type DraftAssistantStatus = 'connecting' | 'ready' | 'unavailable';

const DRAFT_POLL_MS = 1_000;
const MAX_CONSECUTIVE_POLL_FAILURES = 30;

function isAssistantUnavailable(error: unknown) {
  return (
    error instanceof WorkspaceApiError &&
    draftAssistantErrorStatus(error.code) === 503
  );
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function isTransientPollFailure(error: unknown) {
  return (
    error instanceof TypeError ||
    (error instanceof WorkspaceApiError &&
      [502, 503, 504].includes(error.status))
  );
}

function waitForPollInterval(signal: AbortSignal) {
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
    }, DRAFT_POLL_MS);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

// The primary transport: the turn runs server-side against the Controller's
// durable operation record, and the browser observes it with short polls.
// Completion truth lives in that record, never in a connection's lifetime, so
// transient poll failures are retried instead of being treated as terminal.
async function pollDraftOperation(
  workspaceId: string,
  operationId: string,
  signal: AbortSignal,
  onSteps: (steps: DraftProgressActivity[]) => void
) {
  let consecutiveFailures = 0;
  while (true) {
    let operation;
    try {
      operation = await getWorkspaceDraftOperation(
        workspaceId,
        operationId,
        signal
      );
      consecutiveFailures = 0;
    } catch (caught) {
      if (signal.aborted || !isTransientPollFailure(caught)) throw caught;
      consecutiveFailures += 1;
      if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) throw caught;
      await waitForPollInterval(signal);
      continue;
    }
    if (operation.state === 'running') {
      onSteps(operation.steps);
      await waitForPollInterval(signal);
      continue;
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
  // The completion handler needs the dirty state at completion time, not the
  // value captured when the turn was submitted.
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const savedDraftVersionRef = useRef(savedDraft?.draftVersion ?? 0);
  savedDraftVersionRef.current = savedDraft?.draftVersion ?? 0;

  useEffect(
    () => () => {
      requestControllerRef.current?.abort();
    },
    []
  );

  const applyOperationResult = useCallback(
    async (operationId: string, controller: AbortController) => {
      const result = await pollDraftOperation(
        workspaceId,
        operationId,
        controller.signal,
        (steps) => {
          progressRef.current = steps;
          setProgress(steps);
        }
      );
      setStatus('ready');
      if (result.draftChanged) {
        if (dirtyRef.current) {
          // Conflict beats clobber: never overwrite live local edits with
          // the assistant's result. The saved version is on the server; the
          // member's next Save resolves through the existing conflict flow.
          toast(
            `The assistant saved Draft v${result.draftVersion}. Your ` +
              'unsaved edits are untouched; save or discard them to load it.'
          );
        } else {
          const context = await getWorkspaceContext(
            workspaceId,
            controller.signal
          );
          const actualDraftVersion = context.draft?.draftVersion ?? 0;
          if (actualDraftVersion !== result.draftVersion) {
            throw new WorkspaceApiError(
              409,
              'The saved Draft changed again before it could be loaded.',
              'version_conflict',
              'draft'
            );
          }
          try {
            await onDraftChanged(context);
          } catch (caught) {
            const failure = errorMessage(
              caught,
              'The Draft was saved, but the updated preview could not be loaded.'
            );
            onError(failure);
            toast.error(failure);
          }
        }
      }
      setConversation((current) => ({
        workspaceId,
        messages: [
          ...(current?.messages ?? []),
          {
            role: 'assistant',
            text: result.reply,
            turnId: operationId,
            ...(result.steps.length > 0 ? { steps: result.steps } : {}),
          },
        ],
      }));
    },
    [onDraftChanged, onError, workspaceId]
  );

  const resumeOperation = useCallback(
    (operationId: string, initialSteps: DraftProgressActivity[]) => {
      const controller = new AbortController();
      requestControllerRef.current = controller;
      setPending(true);
      progressRef.current = initialSteps;
      setProgress(initialSteps);
      onError(null);
      void (async () => {
        try {
          await applyOperationResult(operationId, controller);
        } catch (caught) {
          if (controller.signal.aborted) return;
          if (
            caught instanceof WorkspaceApiError &&
            caught.code === 'version_conflict' &&
            caught.versionKind === 'draft'
          ) {
            onConflict();
            return;
          }
          if (isAssistantUnavailable(caught)) {
            setStatus('unavailable');
          }
          const failure = errorMessage(
            caught,
            'The Draft Assistant could not complete the request.'
          );
          onError(failure);
          toast.error(failure);
        } finally {
          if (requestControllerRef.current === controller) {
            requestControllerRef.current = null;
          }
          setProgress([]);
          progressRef.current = [];
          setPending(false);
        }
      })();
    },
    [applyOperationResult, onConflict, onError]
  );

  // A turn can complete while nobody is polling (mid-turn refresh, another
  // tab, a stage switch): the ledger then shows the result, but the editor
  // still holds the context loaded before the save. Converge it to the
  // saved Draft the turn produced.
  const settleSavedDraft = useCallback(
    (serverDraftVersion: number | undefined) => {
      if (
        typeof serverDraftVersion !== 'number' ||
        serverDraftVersion <= savedDraftVersionRef.current
      ) {
        return;
      }
      if (dirtyRef.current) {
        // Conflict beats clobber, same as the live completion path.
        toast(
          `The assistant saved Draft v${serverDraftVersion}. Your ` +
            'unsaved edits are untouched; save or discard them to load it.'
        );
        return;
      }
      void getWorkspaceContext(workspaceId)
        .then((context) => onDraftChanged(context))
        .catch((caught) => {
          const failure = errorMessage(
            caught,
            'The assistant saved a new Draft, but it could not be loaded.'
          );
          onError(failure);
          toast.error(failure);
        });
    },
    [onDraftChanged, onError, workspaceId]
  );

  useEffect(() => {
    if (!active || conversation) return;
    const requestId = ++historyRequestIdRef.current;
    void getWorkspaceDraftConversation(workspaceId)
      .then((history) => {
        if (historyRequestIdRef.current !== requestId) return;
        const running = history.activeOperation;
        if (!running) {
          setConversation(history);
          setStatus('ready');
          settleSavedDraft(history.draftVersion);
          return;
        }
        // A turn is still running server-side (this tab refreshed, or it was
        // submitted from another tab). Show its user message and reattach by
        // polling — never resubmit.
        setConversation({
          workspaceId,
          messages: [
            ...history.messages,
            {
              role: 'user',
              text: running.memberMessage,
              ...(running.selectedText
                ? { selectedText: running.selectedText }
                : {}),
            },
          ],
        });
        setStatus('ready');
        resumeOperation(running.operationId, running.steps);
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
  }, [active, conversation, resumeOperation, settleSavedDraft, workspaceId]);

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
      try {
        await submitWorkspaceDraftChat(
          workspaceId,
          {
            expectedManifestVersion: manifestVersion,
            expectedDraftVersion: savedDraft.draftVersion,
            operationId,
            message: request,
            selectedText,
          },
          requestController.signal
        );
      } catch (submitError) {
        // A network failure may have lost only the response: if the submit
        // reached the Controller the operation exists, so try to attach to
        // it before reporting the failure.
        if (!(submitError instanceof TypeError)) throw submitError;
        try {
          await applyOperationResult(operationId, requestController);
          return;
        } catch (pollError) {
          throw pollError instanceof WorkspaceApiError &&
            pollError.code === 'draft_operation_not_found'
            ? submitError
            : pollError;
        }
      }
      await applyOperationResult(operationId, requestController);
    } catch (caught) {
      if (requestController.signal.aborted) return;
      setMessage(request);
      setConversation((current) =>
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
      if (isAssistantUnavailable(caught)) {
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
    applyOperationResult,
    dirty,
    manifestVersion,
    message,
    onConflict,
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
