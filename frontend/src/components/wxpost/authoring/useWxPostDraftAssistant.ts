'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import {
  draftAssistantErrorStatus,
  getWorkspaceContext,
  getWorkspaceDraftConversation,
  interruptWorkspaceDraftOperation,
  pollWorkspaceDraftOperation,
  submitWorkspaceDraftChat,
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
  const [stopPending, setStopPending] = useState(false);
  const progressRef = useRef<DraftProgressActivity[]>([]);
  const requestControllerRef = useRef<AbortController | null>(null);
  // The operation the running poll is attached to, so Stop can target it.
  const activeOperationIdRef = useRef<string | null>(null);
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
      activeOperationIdRef.current = operationId;
      const result = await pollWorkspaceDraftOperation(
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
            caught.code === 'draft_turn_interrupted'
          ) {
            toast('Stopped the Draft Assistant turn.');
            return;
          }
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
          activeOperationIdRef.current = null;
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

  const adoptConversation = useCallback(
    (history: WorkspaceDraftConversation) => {
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
    },
    [resumeOperation, settleSavedDraft, workspaceId]
  );

  useEffect(() => {
    if (!active || conversation) return;
    const requestId = ++historyRequestIdRef.current;
    void getWorkspaceDraftConversation(workspaceId)
      .then((history) => {
        if (historyRequestIdRef.current !== requestId) return;
        adoptConversation(history);
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
  }, [active, adoptConversation, conversation, workspaceId]);

  // A tab that did not submit the running turn has no push channel. When it
  // becomes visible again, re-read the conversation: adopt turns finished
  // elsewhere (which also settles the editor) and reattach to one still
  // running. Skipped while this tab's own poll is attached.
  useEffect(() => {
    if (!active) return;
    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return;
      if (requestControllerRef.current) return;
      const requestId = ++historyRequestIdRef.current;
      void getWorkspaceDraftConversation(workspaceId)
        .then((history) => {
          if (historyRequestIdRef.current !== requestId) return;
          if (requestControllerRef.current) return;
          adoptConversation(history);
        })
        .catch(() => undefined);
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () =>
      document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [active, adoptConversation, workspaceId]);

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
        caught.code === 'draft_turn_interrupted'
      ) {
        // The member asked for the stop; their message is back in the
        // composer for a retry, so this is not an error.
        toast('Stopped the Draft Assistant turn.');
        return;
      }
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
      activeOperationIdRef.current = null;
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

  const stop = useCallback(async () => {
    const operationId = activeOperationIdRef.current;
    if (!operationId || stopPending) return;
    setStopPending(true);
    try {
      // Only signals the stop: the running poll keeps observing the
      // operation and reports how it actually ended (stopped, or completed
      // because the save landed first).
      await interruptWorkspaceDraftOperation(workspaceId, operationId);
    } catch (caught) {
      toast.error(
        errorMessage(caught, 'The Draft Assistant turn could not be stopped.')
      );
    } finally {
      setStopPending(false);
    }
  }, [stopPending, workspaceId]);

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
    stopPending,
    progress,
    setMessage,
    send,
    stop,
    reset,
  };
}
