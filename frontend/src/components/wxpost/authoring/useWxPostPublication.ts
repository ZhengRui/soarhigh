'use client';

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';

import {
  getWorkspacePublication,
  syncWorkspacePublication,
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

  const sync = useCallback(async () => {
    if (!savedDraft || !status || dirty) return;
    setPending(true);
    try {
      const next = await syncWorkspacePublication(workspaceId, {
        expectedManifestVersion: manifestVersion,
        expectedDraftVersion: savedDraft.draftVersion,
        expectedPublicRevision: status.publicRevision,
      });
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
        status.state === 'not-synced'
          ? 'Public WxPost published successfully!'
          : 'Public WxPost updated successfully!'
      );
    } catch (caught) {
      if (
        caught instanceof WorkspaceApiError &&
        (caught.code === 'version_conflict' || caught.status === 409)
      ) {
        onConflict();
        return;
      }
      toast.error(
        errorMessage(caught, 'Unable to synchronize the public WxPost.')
      );
    } finally {
      setPending(false);
    }
  }, [
    dirty,
    manifestVersion,
    onConflict,
    queryClient,
    savedDraft,
    status,
    workspaceId,
  ]);

  return { status, loading, loadError, pending, sync };
}
