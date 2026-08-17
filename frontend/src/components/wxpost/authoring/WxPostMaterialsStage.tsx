'use client';

import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Loader2, RefreshCw, Save } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import { listMeetingMedia, type MediaFileList } from '@/utils/alicloud';
import { useMeeting } from '@/hooks/useMeeting';
import type { MeetingIF } from '@/interfaces';
import {
  WorkspaceApiError,
  deleteWorkspaceSource,
  getWorkspaceContext,
  importWorkspaceSource,
  preflightWorkspaceSourceDelete,
  saveWorkspaceMaterials,
  suggestWorkspaceSourceDescription,
  syncWorkspaceMeetingMedia,
  uploadWorkspaceSource,
  type WorkspaceContext,
  type WorkspaceDeletePreflight,
  type WorkspaceEditorial,
  type WorkspaceManifest,
  type WorkspaceSourceUpdate,
} from '@/utils/wxpostWorkspace';

import { ArticleInputsPanel } from './ArticleInputsPanel';
import { MeetingContextPanel } from './MeetingContextPanel';
import { MaterialsPanel } from './MaterialsPanel';
import type { WxPostMaterial, WxPostMaterialsWorkingCopy } from './types';
import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';
import { WorkspaceConflictDialog } from './WorkspaceConflictDialog';

type LinkedMeeting = MeetingIF & { id: string };
type PendingOperation = {
  kind: 'import' | 'upload' | 'delete';
  sourceId: string | null;
};

function materialsEditorial(
  workingCopy: WxPostMaterialsWorkingCopy
): WorkspaceEditorial {
  return {
    articleType: workingCopy.articleType,
    customArticleType:
      workingCopy.articleType === 'custom'
        ? workingCopy.customArticleType.trim() || null
        : null,
    writingApproach: workingCopy.writingApproach,
    transcript: workingCopy.transcript,
    extraNotes: workingCopy.extraNotes,
    writingGuidance: workingCopy.writingGuidance,
    voiceTone: {
      presets: workingCopy.voiceTonePresets,
      customProfiles: workingCopy.customVoiceToneProfiles,
    },
  };
}

function editorialsMatch(
  current: WorkspaceEditorial,
  next: WorkspaceEditorial
) {
  return (
    current.articleType === next.articleType &&
    current.customArticleType === next.customArticleType &&
    current.writingApproach === next.writingApproach &&
    current.transcript === next.transcript &&
    current.extraNotes === next.extraNotes &&
    current.writingGuidance === next.writingGuidance &&
    JSON.stringify(current.voiceTone) === JSON.stringify(next.voiceTone)
  );
}

function materialsSourceUpdates(
  context: WorkspaceContext,
  workingCopy: WxPostMaterialsWorkingCopy
) {
  return context.manifest.sources.flatMap<WorkspaceSourceUpdate>((source) => {
    const workingSource = workingCopy.sources[source.id];
    if (!workingSource) return [];

    const hasDescription = workingSource.description.trim().length > 0;
    return [
      {
        sourceId: source.id,
        included: workingSource.included,
        description: hasDescription ? workingSource.description : '',
        descriptionSource: hasDescription
          ? workingSource.descriptionSource
          : null,
        descriptionStatus: hasDescription
          ? workingSource.descriptionStatus === 'needs_confirmation'
            ? 'confirmed'
            : workingSource.descriptionStatus
          : 'missing',
      },
    ];
  });
}

function materialSourcesMatch(
  context: WorkspaceContext,
  workingCopy: WxPostMaterialsWorkingCopy
) {
  return context.manifest.sources.every((source) => {
    const workingSource = workingCopy.sources[source.id];
    const savedDescriptionStatus =
      workingSource?.description.trim() &&
      workingSource.descriptionStatus === 'needs_confirmation'
        ? 'confirmed'
        : workingSource?.descriptionStatus;
    return (
      workingSource &&
      workingSource.included === source.included &&
      workingSource.description === source.description &&
      workingSource.descriptionSource === source.descriptionSource &&
      savedDescriptionStatus === source.descriptionStatus
    );
  });
}

export function WxPostMaterialsStage({
  active,
  workspaceId,
  context,
  onContextChange,
  workingCopy,
  onWorkingCopyChange,
  onGenerateDraft,
  draftGenerationPending,
  onOpenDraft,
}: {
  active: boolean;
  workspaceId: string;
  context: WorkspaceContext;
  onContextChange: (
    context: WorkspaceContext,
    options?: { resetWorkingCopy?: boolean }
  ) => void;
  workingCopy: WxPostMaterialsWorkingCopy;
  onWorkingCopyChange: (
    updater: (current: WxPostMaterialsWorkingCopy) => WxPostMaterialsWorkingCopy
  ) => void;
  onGenerateDraft: () => Promise<void>;
  draftGenerationPending: boolean;
  onOpenDraft: () => void;
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
  const [materialsSavePending, setMaterialsSavePending] = useState(false);
  const [describingSourceIds, setDescribingSourceIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [versionConflict, setVersionConflict] = useState(false);
  const [conflictRefreshPending, setConflictRefreshPending] = useState(false);
  const [conflictRefreshError, setConflictRefreshError] = useState<
    string | null
  >(null);
  const busy =
    pendingOperation !== null || materialsSavePending || versionConflict;
  const descriptionPending = describingSourceIds.size > 0;
  const [operationError, setOperationError] = useState<string | null>(null);
  const meetingPreviewsLoading =
    active &&
    Boolean(meetingId) &&
    (meetingQuery.isPending ||
      (Boolean(meeting?.id) &&
        (mediaQuery.isPending || mediaQuery.isFetching)));

  useEffect(() => {
    contextRef.current = context;
  }, [context]);

  // The manifest snapshots the meeting library at workspace creation, so
  // media uploaded to the meeting afterwards have no source record. Sync
  // once per workspace when the stage opens; a failed sync just leaves the
  // known candidates in place.
  const syncedMeetingMediaFor = useRef<string | null>(null);
  const onContextChangeRef = useRef(onContextChange);
  useEffect(() => {
    onContextChangeRef.current = onContextChange;
  }, [onContextChange]);
  useEffect(() => {
    if (!active || !meetingId) return;
    if (syncedMeetingMediaFor.current === workspaceId) return;
    syncedMeetingMediaFor.current = workspaceId;
    void syncWorkspaceMeetingMedia(workspaceId)
      .then((refreshed) => onContextChangeRef.current(refreshed))
      .catch(() => undefined);
  }, [active, meetingId, workspaceId]);

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
        previewLoading:
          source.origin.type === 'meeting-library' &&
          !source.workspaceReady &&
          !mediaUrls.has(source.origin.fileKey) &&
          meetingPreviewsLoading,
        filename: source.filename,
        description:
          workingCopy.sources[source.id]?.description ?? source.description,
        workspaceReady: source.workspaceReady,
        contentSha256: source.contentSha256,
        included: workingCopy.sources[source.id]?.included ?? source.included,
      }));
  }, [
    context.manifest.sources,
    mediaQuery.data?.items,
    meetingPreviewsLoading,
    workingCopy.sources,
  ]);
  const pendingEditorial = useMemo(
    () => materialsEditorial(workingCopy),
    [workingCopy]
  );
  const pendingSourceUpdates = useMemo(
    () => materialsSourceUpdates(context, workingCopy),
    [context, workingCopy]
  );
  const materialsDirty =
    !editorialsMatch(context.manifest.editorial, pendingEditorial) ||
    !materialSourcesMatch(context, workingCopy);

  const updateWorkingCopy = useCallback(
    (updates: Partial<WxPostMaterialsWorkingCopy>) => {
      onWorkingCopyChange((current) => ({ ...current, ...updates }));
    },
    [onWorkingCopyChange]
  );

  const updateSourceWorkingState = useCallback(
    (
      sourceId: string,
      updates: Partial<WxPostMaterialsWorkingCopy['sources'][string]>
    ) => {
      const source = contextRef.current.manifest.sources.find(
        (item) => item.id === sourceId
      );
      onWorkingCopyChange((current) => {
        const currentSource = current.sources[sourceId] ?? {
          included: source?.included ?? false,
          description: source?.description ?? '',
          descriptionSource: source?.descriptionSource ?? null,
          descriptionStatus: source?.descriptionStatus ?? 'missing',
        };
        return {
          ...current,
          sources: {
            ...current.sources,
            [sourceId]: { ...currentSource, ...updates },
          },
        };
      });
    },
    [onWorkingCopyChange]
  );

  const applyManifest = useCallback(
    (manifest: WorkspaceManifest) => {
      const updated = { ...contextRef.current, manifest };
      contextRef.current = updated;
      onContextChange(updated);
    },
    [onContextChange]
  );

  const refreshContext = useCallback(
    async (resetWorkingCopy = false) => {
      const refreshed = await getWorkspaceContext(workspaceId);
      contextRef.current = refreshed;
      onContextChange(refreshed, { resetWorkingCopy });
      return refreshed;
    },
    [onContextChange, workspaceId]
  );

  const showVersionConflict = useCallback(() => {
    setConflictRefreshError(null);
    setVersionConflict(true);
  }, []);

  const runMutation = useCallback(
    (
      pending: PendingOperation,
      operation: (expectedManifestVersion: number) => Promise<WorkspaceManifest>
    ) => {
      const task = operationQueue.current.then(async () => {
        setPendingOperation(pending);
        setOperationError(null);
        try {
          const manifest = await operation(
            contextRef.current.manifest.manifestVersion
          );
          applyManifest(manifest);
          return manifest;
        } catch (error) {
          if (
            error instanceof WorkspaceApiError &&
            error.code === 'version_conflict'
          ) {
            showVersionConflict();
          } else if (
            error instanceof WorkspaceApiError &&
            error.code === 'source_referenced_by_draft'
          ) {
            // The Draft began referencing this source after preflight. The
            // material dialog refreshes its dependency state in-place.
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
    [applyManifest, showVersionConflict]
  );

  const keepCurrentEdits = useCallback(() => {
    if (!versionConflict) return;
    setVersionConflict(false);
    setConflictRefreshError(null);
  }, [versionConflict]);

  const loadLatestMaterials = useCallback(async () => {
    setConflictRefreshPending(true);
    setConflictRefreshError(null);
    try {
      await refreshContext(true);
      setVersionConflict(false);
    } catch {
      setConflictRefreshError(
        'The latest materials could not be loaded. Your current edits are still here.'
      );
    } finally {
      setConflictRefreshPending(false);
    }
  }, [refreshContext]);

  async function handleSaveMaterials() {
    if (!materialsDirty || materialsSavePending || pendingOperation) return;
    onWorkingCopyChange((current) => ({
      ...current,
      customArticleType:
        current.articleType === 'custom'
          ? current.customArticleType.trim()
          : current.customArticleType,
      sources: Object.fromEntries(
        Object.entries(current.sources).map(([sourceId, source]) => [
          sourceId,
          {
            ...source,
            description:
              source.description.trim().length > 0 ? source.description : '',
          },
        ])
      ),
    }));
    setMaterialsSavePending(true);
    setOperationError(null);
    try {
      const updated = await saveWorkspaceMaterials(workspaceId, {
        expectedManifestVersion: contextRef.current.manifest.manifestVersion,
        meetingId: context.manifest.meetingId,
        editorial: pendingEditorial,
        sourceUpdates: pendingSourceUpdates,
      });
      contextRef.current = updated;
      onContextChange(updated, { resetWorkingCopy: true });
      toast.success('Materials saved successfully!');
    } catch (error) {
      if (
        error instanceof WorkspaceApiError &&
        error.code === 'version_conflict'
      ) {
        showVersionConflict();
      } else {
        toast.error(
          error instanceof Error
            ? error.message
            : 'The materials could not be saved.'
        );
      }
    } finally {
      setMaterialsSavePending(false);
    }
  }

  const generateDraft = useCallback(async () => {
    try {
      await onGenerateDraft();
    } catch (error) {
      if (
        error instanceof WorkspaceApiError &&
        error.code === 'version_conflict'
      ) {
        showVersionConflict();
      }
    }
  }, [onGenerateDraft, showVersionConflict]);

  const generateDescription = useCallback(
    async (sourceId: string) => {
      if (describingSourceIds.has(sourceId)) return;

      const source = contextRef.current.manifest.sources.find(
        (item) => item.id === sourceId
      );
      if (!source || source.kind !== 'image' || !source.workspaceReady) return;

      const currentDescription =
        workingCopy.sources[sourceId]?.description ?? source.description;
      setDescribingSourceIds((current) => new Set(current).add(sourceId));
      setOperationError(null);
      try {
        const suggestion = await suggestWorkspaceSourceDescription(
          workspaceId,
          sourceId,
          contextRef.current.manifest.manifestVersion,
          currentDescription
        );
        updateSourceWorkingState(sourceId, {
          description: suggestion.description,
          descriptionSource: 'ai',
          descriptionStatus: 'needs_confirmation',
        });
      } catch (error) {
        if (
          error instanceof WorkspaceApiError &&
          error.code === 'version_conflict'
        ) {
          showVersionConflict();
        } else {
          toast.error(
            error instanceof Error
              ? error.message
              : 'The image description could not be generated.'
          );
        }
      } finally {
        setDescribingSourceIds((current) => {
          const next = new Set(current);
          next.delete(sourceId);
          return next;
        });
      }
    },
    [
      describingSourceIds,
      showVersionConflict,
      updateSourceWorkingState,
      workingCopy.sources,
      workspaceId,
    ]
  );

  return (
    <div className='grid gap-5 max-[480px]:gap-3' data-testid='materials-stage'>
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
        describingSourceIds={describingSourceIds}
        onImport={async (sourceId) => {
          await runMutation({ kind: 'import', sourceId }, (version) =>
            importWorkspaceSource(workspaceId, sourceId, version)
          );
        }}
        onToggleIncluded={async (sourceId, included) => {
          const source = contextRef.current.manifest.sources.find(
            (item) => item.id === sourceId
          );
          if (included && !source?.workspaceReady) {
            await runMutation({ kind: 'import', sourceId }, (version) =>
              importWorkspaceSource(workspaceId, sourceId, version)
            );
          }
          updateSourceWorkingState(sourceId, { included });
        }}
        onDescriptionChange={(sourceId, description) =>
          updateSourceWorkingState(sourceId, {
            description,
            descriptionSource: description.trim() ? 'user' : null,
            descriptionStatus: description.trim() ? 'confirmed' : 'missing',
          })
        }
        onGenerateDescription={generateDescription}
        onUpload={async (file) => {
          await runMutation({ kind: 'upload', sourceId: null }, (version) =>
            uploadWorkspaceSource(workspaceId, version, file)
          );
        }}
        onDeletePreflight={async (sourceId) => {
          try {
            return await preflightWorkspaceSourceDelete(
              workspaceId,
              sourceId,
              contextRef.current.manifest.manifestVersion
            );
          } catch (error) {
            if (
              error instanceof WorkspaceApiError &&
              error.code === 'version_conflict'
            ) {
              showVersionConflict();
            }
            throw error;
          }
        }}
        onDelete={async (
          sourceId: string,
          preflight: WorkspaceDeletePreflight
        ) => {
          const manifest = await runMutation({ kind: 'delete', sourceId }, () =>
            deleteWorkspaceSource(
              workspaceId,
              sourceId,
              preflight.manifestVersion
            )
          );
          if (manifest.sources.some((source) => source.id === sourceId)) {
            updateSourceWorkingState(sourceId, { included: false });
          }
        }}
        onOpenDraft={onOpenDraft}
      />
      <ArticleInputsPanel
        workspaceId={workspaceId}
        writingApproach={workingCopy.writingApproach}
        voiceTonePresets={workingCopy.voiceTonePresets}
        customVoiceToneProfiles={workingCopy.customVoiceToneProfiles}
        transcript={workingCopy.transcript}
        extraNotes={workingCopy.extraNotes}
        writingGuidance={workingCopy.writingGuidance}
        onWritingApproachChange={(writingApproach) =>
          updateWorkingCopy({ writingApproach })
        }
        onVoiceTonePresetsChange={(voiceTonePresets) =>
          updateWorkingCopy({ voiceTonePresets })
        }
        onCustomVoiceToneProfilesChange={(customVoiceToneProfiles) =>
          updateWorkingCopy({ customVoiceToneProfiles })
        }
        onTranscriptChange={(transcript) => updateWorkingCopy({ transcript })}
        onExtraNotesChange={(extraNotes) => updateWorkingCopy({ extraNotes })}
        onWritingGuidanceChange={(writingGuidance) =>
          updateWorkingCopy({ writingGuidance })
        }
      />

      <div className='flex items-center justify-end gap-[10px] pt-0.5 max-[760px]:[&_button]:flex-1 max-[480px]:flex-col max-[480px]:[&_button]:w-full'>
        <button
          type='button'
          className={SECONDARY_BUTTON_CLASS}
          disabled={!materialsDirty || busy}
          onClick={() => void handleSaveMaterials()}
          data-testid='save-materials'
        >
          {materialsSavePending ? (
            <Loader2 className='animate-spin' aria-hidden='true' />
          ) : (
            <Save aria-hidden='true' />
          )}
          {materialsSavePending ? 'Saving…' : 'Save Materials'}
        </button>
        <button
          type='button'
          className={PRIMARY_BUTTON_CLASS}
          disabled={
            materialsDirty ||
            busy ||
            descriptionPending ||
            draftGenerationPending
          }
          title={
            materialsDirty
              ? 'Save Materials before generating the draft.'
              : undefined
          }
          onClick={() => void generateDraft()}
          data-testid='generate-draft'
        >
          {draftGenerationPending && (
            <Loader2 className='animate-spin' aria-hidden='true' />
          )}
          {draftGenerationPending
            ? context.draft
              ? 'Regenerating…'
              : 'Generating…'
            : context.draft
              ? 'Regenerate Draft'
              : 'Generate Draft'}
          <ArrowRight aria-hidden='true' />
        </button>
      </div>

      {versionConflict && (
        <WorkspaceConflictDialog
          title='Load latest materials?'
          error={conflictRefreshError}
          pending={conflictRefreshPending}
          testId='materials-conflict-dialog'
          onKeepCurrent={keepCurrentEdits}
          onLoadLatest={() => void loadLatestMaterials()}
        >
          This workspace changed since this page loaded. Loading the latest
          version will discard your unsaved changes on this page. The action you
          just attempted was not applied.
        </WorkspaceConflictDialog>
      )}
    </div>
  );
}
