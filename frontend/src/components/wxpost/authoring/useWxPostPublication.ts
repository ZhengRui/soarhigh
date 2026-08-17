'use client';

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import {
  getRunningPublicationOperation,
  getWorkspacePublication,
  pollWorkspacePublicationOperation,
  submitWorkspacePublicationSync,
  WorkspaceApiError,
  type WorkspaceContext,
  type WorkspacePublicationStatus,
} from '@/utils/wxpostWorkspace';

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function useWxPostPublication({
  active,
  workspaceId,
  manifestVersion,
  savedDraft,
  dirty,
  onConflict,
}: {
  active: boolean;
  workspaceId: string;
  manifestVersion: number;
  savedDraft: WorkspaceContext['draft'];
  dirty: boolean;
  onConflict: () => void;
}) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<WorkspacePublicationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [pending, setPending] = useState(false);
  // The operation the currently attached poll is watching, whether started
  // by this tab's own submit or reattached to one already running
  // server-side. Aborting it only stops this tab from watching — the
  // publication continues running on the Controller.
  const pollControllerRef = useRef<AbortController | null>(null);
  const statusRef = useRef<WorkspacePublicationStatus | null>(null);
  statusRef.current = status;
  // The panel's caller passes an inline arrow for onConflict, so its
  // identity changes on every render of the parent (block clicks, selection
  // changes, setDocument, ...). Read it through a ref so the resume effect
  // below can key off [active, workspaceId] alone instead of re-running
  // (and re-fetching the running-operation check) on every unrelated
  // parent render.
  const onConflictRef = useRef(onConflict);
  onConflictRef.current = onConflict;

  useEffect(() => () => pollControllerRef.current?.abort(), []);

  useEffect(() => {
    if (!active || !savedDraft) return;
    let current = true;
    setLoading(true);
    setLoadError(false);
    void getWorkspacePublication(workspaceId)
      .then((publication) => {
        if (current) setStatus(publication);
      })
      .catch((caught) => {
        if (!current) return;
        setStatus(null);
        setLoadError(true);
        toast.error(
          errorMessage(caught, 'Unable to check the public WxPost status.')
        );
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [active, savedDraft, workspaceId]);

  const applyPublicationResult = useCallback(
    (next: WorkspacePublicationStatus) => {
      // Read the wording state right before it flips: status can't change
      // mid-poll except through this very operation completing, so this is
      // still "the state before this publish" for both a fresh submit (where
      // it was loaded before the button was even enabled) and a resumed one
      // (where the mount-time status fetch may still be in flight when the
      // poll attaches, but has settled by the time it resolves).
      const priorState = statusRef.current?.state;
      setStatus(next);
      void queryClient.invalidateQueries({
        queryKey: ['wxpost-workspaces'],
        refetchType: 'none',
      });
      void queryClient.invalidateQueries({ queryKey: ['posts'] });
      if (next.slug) {
        void queryClient.invalidateQueries({
          queryKey: ['wxpost', next.slug],
          refetchType: 'none',
        });
      }
      toast.success(
        priorState === 'not-synced'
          ? 'Public WxPost published successfully!'
          : 'Public WxPost updated successfully!'
      );
    },
    [queryClient]
  );

  // Attach a poll to an operation already admitted server-side (this tab's
  // own submit, or one reattached on mount) and report the outcome the same
  // way a fresh submit does.
  const watchOperation = useCallback(
    async (operationId: string, controller: AbortController) => {
      const next = await pollWorkspacePublicationOperation(
        workspaceId,
        operationId,
        controller.signal
      );
      applyPublicationResult(next);
    },
    [applyPublicationResult, workspaceId]
  );
  const watchOperationRef = useRef(watchOperation);
  watchOperationRef.current = watchOperation;

  // Resume-on-mount: a publish can outlive the tab that submitted it (a
  // refresh, or another tab). When the publication panel becomes active,
  // check for an operation still running server-side and reattach instead
  // of leaving the panel to think nothing is happening.
  //
  // Deps are intentionally just [active, savedDraft, workspaceId]: onConflict
  // and watchOperation are read through refs so an unrelated re-render of the
  // Draft stage (which passes onConflict as a fresh inline arrow every time)
  // doesn't re-fire the running-operation check.
  useEffect(() => {
    if (!active || !savedDraft) return;
    let current = true;
    void getRunningPublicationOperation(workspaceId)
      .then((response) => {
        if (!current || !response.running || pollControllerRef.current) {
          return;
        }
        const controller = new AbortController();
        pollControllerRef.current = controller;
        setPending(true);
        void watchOperationRef
          .current(response.running.operationId, controller)
          .catch((caught) => {
            if (controller.signal.aborted) return;
            if (
              caught instanceof WorkspaceApiError &&
              caught.code === 'version_conflict'
            ) {
              onConflictRef.current();
              return;
            }
            toast.error(
              errorMessage(caught, 'Unable to synchronize the public WxPost.')
            );
          })
          .finally(() => {
            if (pollControllerRef.current === controller) {
              pollControllerRef.current = null;
            }
            setPending(false);
          });
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [active, savedDraft, workspaceId]);

  const sync = useCallback(async () => {
    if (!savedDraft || !status || dirty || pollControllerRef.current) return;
    const operationId = `publish-${crypto.randomUUID().replaceAll('-', '')}`;
    const controller = new AbortController();
    pollControllerRef.current = controller;
    setPending(true);
    try {
      await submitWorkspacePublicationSync(workspaceId, {
        operationId,
        expectedManifestVersion: manifestVersion,
        expectedDraftVersion: savedDraft.draftVersion,
        expectedPublicRevision: status.publicRevision,
      });
      await watchOperation(operationId, controller);
    } catch (caught) {
      if (controller.signal.aborted) return;
      if (
        caught instanceof WorkspaceApiError &&
        caught.code === 'version_conflict'
      ) {
        onConflictRef.current();
        return;
      }
      toast.error(
        errorMessage(caught, 'Unable to synchronize the public WxPost.')
      );
    } finally {
      if (pollControllerRef.current === controller) {
        pollControllerRef.current = null;
      }
      setPending(false);
    }
  }, [dirty, manifestVersion, savedDraft, status, watchOperation, workspaceId]);

  return { status, loading, loadError, pending, sync };
}
