'use client';

import { useQuery } from '@tanstack/react-query';
import { ArrowRight, ChevronLeft, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { listMeetingMedia, type MediaFileList } from '@/utils/alicloud';
import { useMeeting } from '@/hooks/useMeeting';
import type { MeetingIF } from '@/interfaces';
import {
  WorkspaceApiError,
  deleteWorkspaceSource,
  getWorkspaceContext,
  importWorkspaceSource,
  preflightWorkspaceSourceDelete,
  setWorkspaceSourceIncluded,
  updateWorkspaceSources,
  uploadWorkspaceSource,
  type WorkspaceContext,
  type WorkspaceDeletePreflight,
  type WorkspaceManifest,
} from '@/utils/wxpostWorkspace';

import { ArticleInputsPanel } from './ArticleInputsPanel';
import { MeetingContextPanel } from './MeetingContextPanel';
import { MaterialsPanel } from './MaterialsPanel';
import type { WxPostMaterial } from './types';
import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';

type LinkedMeeting = MeetingIF & { id: string };
type PendingOperation = {
  kind: 'import' | 'include' | 'description' | 'upload' | 'delete';
  sourceId: string | null;
};

export function WxPostMaterialsStage({
  active,
  workspaceId,
  context,
  onContextChange,
  onBack,
}: {
  active: boolean;
  workspaceId: string;
  context: WorkspaceContext;
  onContextChange: (context: WorkspaceContext) => void;
  onBack: () => void;
}) {
  const meetingId = context.manifest.meetingId;
  const meetingQuery = useMeeting(active && meetingId ? meetingId : undefined);
  const meeting =
    meetingQuery.data?.id === meetingId
      ? (meetingQuery.data as LinkedMeeting)
      : null;
  const mediaQuery = useQuery<MediaFileList>({
    queryKey: ['meeting-media', meeting?.id],
    queryFn: () =>
      listMeetingMedia(meeting?.id as string) as Promise<MediaFileList>,
    enabled: active && Boolean(meeting?.id),
    staleTime: 60 * 1000,
  });
  const contextRef = useRef(context);
  const operationQueue = useRef<Promise<unknown>>(Promise.resolve());
  const [pendingOperation, setPendingOperation] =
    useState<PendingOperation | null>(null);
  const busy = pendingOperation !== null;
  const [operationError, setOperationError] = useState<string | null>(null);
  const [operationNotice, setOperationNotice] = useState<string | null>(null);

  useEffect(() => {
    contextRef.current = context;
  }, [context]);

  const materials = useMemo<WxPostMaterial[]>(() => {
    const mediaUrls = new Map(
      (mediaQuery.data?.items ?? []).map((file) => [file.fileKey, file.url])
    );
    return context.manifest.sources
      .filter((source) => source.kind === 'image' || source.kind === 'video')
      .map((source) => ({
        sourceId: source.id,
        source:
          source.origin.type === 'meeting-library'
            ? ('Meeting Library' as const)
            : source.origin.type === 'feishu-upload'
              ? ('Feishu upload' as const)
              : ('Web upload' as const),
        kind: source.kind === 'image' ? 'image' : 'video',
        previewUrl:
          source.origin.type === 'meeting-library'
            ? (mediaUrls.get(source.origin.fileKey) ?? null)
            : null,
        filename: source.filename,
        description: source.description,
        workspaceReady: source.workspaceReady,
        included: source.included,
      }));
  }, [context.manifest.sources, mediaQuery.data?.items]);

  const applyManifest = useCallback(
    (manifest: WorkspaceManifest) => {
      const updated = { ...contextRef.current, manifest };
      contextRef.current = updated;
      onContextChange(updated);
    },
    [onContextChange]
  );

  const refreshContext = useCallback(async () => {
    const refreshed = await getWorkspaceContext(workspaceId);
    contextRef.current = refreshed;
    onContextChange(refreshed);
    return refreshed;
  }, [onContextChange, workspaceId]);

  const runMutation = useCallback(
    (
      pending: PendingOperation,
      operation: (expectedManifestVersion: number) => Promise<WorkspaceManifest>
    ) => {
      const task = operationQueue.current.then(async () => {
        setPendingOperation(pending);
        setOperationError(null);
        setOperationNotice(null);
        try {
          const manifest = await operation(
            contextRef.current.manifest.manifestVersion
          );
          applyManifest(manifest);
        } catch (error) {
          if (
            error instanceof WorkspaceApiError &&
            error.code === 'version_conflict'
          ) {
            try {
              await refreshContext();
              setOperationNotice(
                'Materials changed in another session. The latest version is now shown; retry your change.'
              );
            } catch {
              setOperationError(
                'Materials changed in another session, but the latest version could not be loaded.'
              );
            }
          } else {
            setOperationError(
              error instanceof Error
                ? error.message
                : 'The material change could not be saved.'
            );
          }
          throw error;
        } finally {
          setPendingOperation(null);
        }
      });
      operationQueue.current = task.catch(() => undefined);
      return task;
    },
    [applyManifest, refreshContext]
  );

  return (
    <div className='grid gap-5' data-testid='materials-stage'>
      {meeting && <MeetingContextPanel meeting={meeting} />}
      {(meetingQuery.isError || mediaQuery.isError) && (
        <div className='flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900'>
          <span>
            {meetingQuery.isError
              ? 'Meeting details are temporarily unavailable.'
              : 'Original meeting previews are temporarily unavailable.'}
          </span>
          <button
            type='button'
            className='inline-flex items-center gap-2 font-bold text-amber-900 hover:underline [&_svg]:h-4 [&_svg]:w-4'
            onClick={() => {
              if (meetingQuery.isError) void meetingQuery.refetch();
              if (mediaQuery.isError) void mediaQuery.refetch();
            }}
          >
            <RefreshCw aria-hidden='true' />
            Retry
          </button>
        </div>
      )}
      {operationError && (
        <p
          className='m-0 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'
          role='alert'
          data-testid='material-operation-error'
        >
          {operationError}
        </p>
      )}
      {operationNotice && (
        <p
          className='m-0 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800'
          role='status'
          data-testid='material-operation-notice'
        >
          {operationNotice}
        </p>
      )}
      <MaterialsPanel
        workspaceId={workspaceId}
        materials={materials}
        busy={busy}
        importingSourceId={
          pendingOperation?.kind === 'import' ? pendingOperation.sourceId : null
        }
        uploading={pendingOperation?.kind === 'upload'}
        deletingSourceId={
          pendingOperation?.kind === 'delete' ? pendingOperation.sourceId : null
        }
        onImport={(sourceId) =>
          runMutation({ kind: 'import', sourceId }, (version) =>
            importWorkspaceSource(workspaceId, sourceId, version)
          )
        }
        onToggleIncluded={(sourceId, included) =>
          runMutation({ kind: 'include', sourceId }, (version) =>
            setWorkspaceSourceIncluded(workspaceId, sourceId, version, included)
          )
        }
        onDescriptionSave={(sourceId, description) =>
          runMutation({ kind: 'description', sourceId }, (version) =>
            updateWorkspaceSources(workspaceId, version, [
              description.trim()
                ? {
                    sourceId,
                    description,
                    descriptionSource: 'user',
                    descriptionStatus: 'confirmed',
                  }
                : {
                    sourceId,
                    description: '',
                    descriptionSource: null,
                    descriptionStatus: 'missing',
                  },
            ])
          )
        }
        onUpload={(file) =>
          runMutation({ kind: 'upload', sourceId: null }, (version) =>
            uploadWorkspaceSource(workspaceId, version, file)
          )
        }
        onDeletePreflight={(sourceId) =>
          preflightWorkspaceSourceDelete(workspaceId, sourceId)
        }
        onDelete={(sourceId: string, preflight: WorkspaceDeletePreflight) =>
          runMutation({ kind: 'delete', sourceId }, () =>
            deleteWorkspaceSource(
              workspaceId,
              sourceId,
              preflight.manifestVersion,
              preflight.requiresConfirmation
            )
          )
        }
      />
      <ArticleInputsPanel key={meetingId ?? 'independent'} />

      <div className='flex items-center justify-end gap-[10px] pt-0.5 max-[760px]:[&_button]:flex-1 max-[480px]:flex-col-reverse max-[480px]:[&_button]:w-full'>
        <button
          type='button'
          className={SECONDARY_BUTTON_CLASS}
          onClick={onBack}
        >
          <ChevronLeft aria-hidden='true' />
          Change setup
        </button>
        <button type='button' className={PRIMARY_BUTTON_CLASS} disabled>
          Generate English draft
          <ArrowRight aria-hidden='true' />
        </button>
      </div>
    </div>
  );
}
