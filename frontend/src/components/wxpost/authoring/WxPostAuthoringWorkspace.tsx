'use client';

import { ArrowLeft, Check, Loader2, PanelsTopLeft } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from 'react';
import toast from 'react-hot-toast';

import { useMeetingOptions } from '@/hooks/useMeetingOptions';
import {
  bootstrapWorkspace,
  generateWorkspaceDraft,
  getWorkspaceContext,
  WORKSPACE_ARTICLE_TYPE_LABELS,
  WorkspaceApiError,
  workspaceEditorPath,
  workspaceListPath,
  type WorkspaceContext,
  type WorkspaceEditorial,
} from '@/utils/wxpostWorkspace';

import type { WxPostAuthoringStage, WxPostMaterialsWorkingCopy } from './types';
import { formatMeetingLabel, isEventMeeting } from './meetingLabels';
import { type LinkedMeetingOption, WxPostSetupStage } from './WxPostSetupStage';
import { WxPostMaterialsStage } from './WxPostMaterialsStage';
import { WxPostDraftStage } from './WxPostDraftStage';
import { STAGE_BUTTON_CLASS } from './authoringStyles';

function createInitialEditorial(
  linked: boolean,
  meeting: LinkedMeetingOption | null
): WorkspaceEditorial {
  const isEvent = linked && isEventMeeting(meeting);

  return {
    articleType: !linked || isEvent ? 'custom' : 'meeting-recap',
    customArticleType: isEvent ? 'Event Recap' : null,
    writingApproach: 'chronological',
    transcript: '',
    extraNotes: '',
    writingGuidance: '',
    voiceTone: {
      presets: [],
      customProfiles: [],
    },
  };
}

function createMaterialsWorkingCopy(
  context: WorkspaceContext
): WxPostMaterialsWorkingCopy {
  return {
    workspaceId: context.workspaceId,
    articleType: context.manifest.editorial.articleType,
    customArticleType: context.manifest.editorial.customArticleType ?? '',
    writingApproach: context.manifest.editorial.writingApproach,
    transcript: context.manifest.editorial.transcript,
    extraNotes: context.manifest.editorial.extraNotes,
    writingGuidance: context.manifest.editorial.writingGuidance,
    voiceTonePresets: context.manifest.editorial.voiceTone.presets,
    customVoiceToneProfiles:
      context.manifest.editorial.voiceTone.customProfiles,
    sources: Object.fromEntries(
      context.manifest.sources.map((source) => [
        source.id,
        {
          included: source.included,
          description: source.description,
        },
      ])
    ),
  };
}

function reconcileMaterialsWorkingCopy(
  current: WxPostMaterialsWorkingCopy | null,
  context: WorkspaceContext
) {
  if (!current || current.workspaceId !== context.workspaceId) {
    return createMaterialsWorkingCopy(context);
  }
  return {
    ...current,
    sources: Object.fromEntries(
      context.manifest.sources.map((source) => [
        source.id,
        current.sources[source.id] ?? {
          included: source.included,
          description: source.description,
        },
      ])
    ),
  };
}

function createWorkspaceId() {
  const suffix = crypto.randomUUID().replaceAll('-', '').slice(0, 12);
  return `wxpost-${suffix}`;
}

function StageTabs({
  stage,
  canOpenMaterials,
  canOpenDraft,
  onStageChange,
}: {
  stage: WxPostAuthoringStage;
  canOpenMaterials: boolean;
  canOpenDraft: boolean;
  onStageChange: (stage: WxPostAuthoringStage) => void;
}) {
  const activeClass =
    'bg-[#eff5ff] text-blue-700 after:absolute after:bottom-0 after:left-[18px] after:right-[18px] after:h-0.5 after:rounded-t-full after:bg-blue-600 [&>span]:bg-blue-600 [&>span]:text-white';

  return (
    <nav
      className='mb-6 grid grid-cols-3 overflow-hidden rounded-[14px] border border-[#d9e1ec] bg-white max-[480px]:mb-4 max-[480px]:rounded-xl'
      aria-label='WxPost authoring progress'
    >
      <button
        type='button'
        aria-current={stage === 'setup' ? 'step' : undefined}
        className={`${STAGE_BUTTON_CLASS} ${
          stage === 'setup'
            ? activeClass
            : 'text-[#245feb] [&>span]:bg-[#e7efff] [&>span]:text-[#245feb]'
        }`}
        onClick={() => onStageChange('setup')}
      >
        <span>{stage !== 'setup' ? <Check /> : '1'}</span>
        Setup
      </button>
      <button
        type='button'
        aria-current={stage === 'materials' ? 'step' : undefined}
        className={`${STAGE_BUTTON_CLASS} ${
          stage === 'materials' ? activeClass : ''
        }`}
        onClick={() => onStageChange('materials')}
        disabled={!canOpenMaterials}
      >
        <span>{stage === 'draft' ? <Check /> : '2'}</span>
        Materials
      </button>
      <button
        type='button'
        aria-current={stage === 'draft' ? 'step' : undefined}
        className={`${STAGE_BUTTON_CLASS} ${
          stage === 'draft'
            ? activeClass
            : !canOpenDraft
              ? 'text-[#a2adbd]'
              : ''
        }`}
        disabled={!canOpenDraft}
        onClick={() => onStageChange('draft')}
      >
        <span>3</span>
        Draft
      </button>
    </nav>
  );
}

export function WxPostAuthoringWorkspace({
  initialWorkspaceId,
}: {
  initialWorkspaceId: string | null;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<WxPostAuthoringStage>(
    initialWorkspaceId ? 'materials' : 'setup'
  );
  const [linked, setLinked] = useState(true);
  const [selectedMeeting, setSelectedMeeting] =
    useState<LinkedMeetingOption | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspaceContext, setWorkspaceContext] =
    useState<WorkspaceContext | null>(null);
  const [materialsWorkingCopy, setMaterialsWorkingCopy] =
    useState<WxPostMaterialsWorkingCopy | null>(null);
  const [workspacePending, setWorkspacePending] = useState(
    Boolean(initialWorkspaceId)
  );
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [syncWorkspaceMeeting, setSyncWorkspaceMeeting] = useState(false);
  const [draftGenerationPending, setDraftGenerationPending] = useState(false);
  const meetingsQuery = useMeetingOptions();

  useLayoutEffect(() => {
    if (initialWorkspaceId) window.scrollTo({ top: 0, left: 0 });
  }, [initialWorkspaceId]);

  const meetings = useMemo(
    () =>
      (meetingsQuery.data?.pages.flatMap((page) => page.items) ?? []).filter(
        (meeting): meeting is LinkedMeetingOption => Boolean(meeting.id)
      ),
    [meetingsQuery.data?.pages]
  );

  const applyWorkspaceContext = useCallback(
    (
      context: WorkspaceContext,
      options: { resetWorkingCopy?: boolean } = {}
    ) => {
      setWorkspaceId(context.workspaceId);
      setWorkspaceContext((current) => {
        const currentDraftState = current?.manifest.draft;
        const nextDraftState = context.manifest.draft;
        const sameSavedDraft =
          current?.workspaceId === context.workspaceId &&
          current.draft !== null &&
          context.draft !== null &&
          currentDraftState != null &&
          nextDraftState != null &&
          currentDraftState.version === nextDraftState.version &&
          currentDraftState.sha256 === nextDraftState.sha256;
        return sameSavedDraft ? { ...context, draft: current.draft } : context;
      });
      setMaterialsWorkingCopy((current) =>
        options.resetWorkingCopy
          ? createMaterialsWorkingCopy(context)
          : reconcileMaterialsWorkingCopy(current, context)
      );
      setLinked(Boolean(context.manifest.meetingId));
      setSelectedMeeting((current) =>
        current?.id === context.manifest.meetingId ? current : null
      );
      setSyncWorkspaceMeeting(Boolean(context.manifest.meetingId));
    },
    []
  );

  const applyChangedWorkspaceContext = useCallback(
    (
      context: WorkspaceContext,
      options: { resetWorkingCopy?: boolean } = {}
    ) => {
      applyWorkspaceContext(context, options);
      void queryClient.invalidateQueries({
        queryKey: ['wxpost-workspaces'],
        refetchType: 'none',
      });
    },
    [applyWorkspaceContext, queryClient]
  );

  useEffect(() => {
    if (!initialWorkspaceId) return;

    let active = true;
    setWorkspacePending(true);
    void getWorkspaceContext(initialWorkspaceId)
      .then((context) => {
        if (!active) return;
        applyWorkspaceContext(context);
        setWorkspaceError(null);
      })
      .catch((error) => {
        if (!active) return;
        setWorkspaceError(
          error instanceof Error
            ? `Unable to resume workspace: ${error.message}`
            : 'Unable to resume workspace.'
        );
      })
      .finally(() => {
        if (active) setWorkspacePending(false);
      });
    return () => {
      active = false;
    };
  }, [applyWorkspaceContext, initialWorkspaceId]);

  useEffect(() => {
    const meetingId = workspaceContext?.manifest.meetingId;
    if (meetingId && syncWorkspaceMeeting) {
      const match = meetings.find((meeting) => meeting.id === meetingId);
      if (match) {
        setSelectedMeeting(match);
        setSyncWorkspaceMeeting(false);
      } else if (
        meetingsQuery.hasNextPage &&
        !meetingsQuery.isFetchingNextPage
      ) {
        void meetingsQuery.fetchNextPage();
      }
      return;
    }
    if (!selectedMeeting && meetings.length > 0) {
      setSelectedMeeting(meetings[0]);
    }
  }, [
    meetings,
    meetingsQuery,
    selectedMeeting,
    syncWorkspaceMeeting,
    workspaceContext?.manifest.meetingId,
  ]);

  const handleCreateWorkspace = useCallback(async () => {
    const meetingId = linked ? (selectedMeeting?.id ?? null) : null;
    if (linked && !meetingId) return;
    const editorial = createInitialEditorial(linked, selectedMeeting);
    const nextWorkspaceId = createWorkspaceId();

    setWorkspacePending(true);
    setWorkspaceError(null);
    try {
      const context = await bootstrapWorkspace(nextWorkspaceId, {
        meetingId,
        editorial,
      });
      await queryClient.invalidateQueries({
        queryKey: ['wxpost-workspaces'],
      });
      router.replace(workspaceEditorPath(context.workspaceId));
    } catch (error) {
      setWorkspaceError(
        error instanceof Error
          ? error.message
          : 'Unable to create the material workspace.'
      );
    } finally {
      setWorkspacePending(false);
    }
  }, [linked, queryClient, router, selectedMeeting]);

  const handleGenerateDraft = useCallback(async () => {
    if (!workspaceContext || !workspaceId) return;
    setDraftGenerationPending(true);
    setWorkspaceError(null);
    try {
      const result = await generateWorkspaceDraft(workspaceId, {
        expectedManifestVersion: workspaceContext.manifest.manifestVersion,
        expectedDraftVersion: workspaceContext.draft?.draftVersion ?? 0,
      });
      applyChangedWorkspaceContext(result.context);
      setStage('draft');
      toast.success(
        workspaceContext.draft
          ? 'Draft regenerated successfully!'
          : 'Draft generated successfully!'
      );
    } catch (error) {
      if (
        error instanceof WorkspaceApiError &&
        error.code === 'version_conflict'
      ) {
        throw error;
      }
      const message =
        error instanceof Error
          ? error.message
          : 'Unable to generate the draft.';
      setWorkspaceError(message);
      toast.error(message);
    } finally {
      setDraftGenerationPending(false);
    }
  }, [applyChangedWorkspaceContext, workspaceContext, workspaceId]);

  const effectiveMeeting = linked ? selectedMeeting : null;
  const canOpenMaterials = Boolean(initialWorkspaceId || workspaceContext);
  const workspaceMeeting =
    workspaceContext?.manifest.meetingId &&
    selectedMeeting?.id === workspaceContext.manifest.meetingId
      ? selectedMeeting
      : null;
  const displayedMeeting =
    stage !== 'setup' ? workspaceMeeting : effectiveMeeting;
  const displayedArticleType =
    stage !== 'setup' ? materialsWorkingCopy?.articleType : null;
  const displayedArticleTypeLabel = displayedArticleType
    ? displayedArticleType === 'custom' &&
      materialsWorkingCopy?.customArticleType.trim()
      ? materialsWorkingCopy.customArticleType.trim()
      : WORKSPACE_ARTICLE_TYPE_LABELS[displayedArticleType]
    : null;
  const headerSubtitlePending = Boolean(
    initialWorkspaceId && !workspaceContext && workspacePending
  );
  const headerSubtitle =
    initialWorkspaceId && !workspaceContext
      ? workspaceError
        ? 'Workspace unavailable'
        : null
      : displayedMeeting
        ? `${formatMeetingLabel(displayedMeeting)}${
            displayedArticleTypeLabel ? ` · ${displayedArticleTypeLabel}` : ''
          }`
        : workspaceContext?.manifest.meetingId && linked
          ? `Linked meeting${
              displayedArticleTypeLabel ? ` · ${displayedArticleTypeLabel}` : ''
            }`
          : `Independent article${
              displayedArticleTypeLabel ? ` · ${displayedArticleTypeLabel}` : ''
            }`;

  return (
    <div className='min-h-screen bg-[#f3f6fa] text-base text-[#172033]'>
      <div
        className='mx-auto w-[min(calc(100%_-_40px),1080px)] py-[34px] pb-[72px] max-[760px]:w-[min(calc(100%_-_24px),1080px)] max-[760px]:pt-6 max-[480px]:w-[min(calc(100%_-_20px),1080px)] max-[480px]:pb-14 max-[480px]:pt-5'
        data-testid='wxpost-page-shell'
      >
        <Link
          href='/posts'
          className='mb-6 inline-flex items-center gap-2 text-sm font-semibold text-[#46556f] no-underline hover:text-[#245feb] max-[480px]:mb-3.5 [&_svg]:h-[17px] [&_svg]:w-[17px]'
        >
          <ArrowLeft aria-hidden='true' />
          Back to Posts
        </Link>

        <header className='mb-8 flex flex-col gap-4 max-[480px]:mb-5 max-[480px]:gap-3 sm:flex-row sm:items-center sm:justify-between'>
          <div>
            <h1 className='mb-2 text-3xl font-bold text-slate-950 max-[480px]:mb-1 max-[480px]:text-2xl sm:mb-4 sm:text-4xl'>
              {initialWorkspaceId ? 'WxPost' : 'New WxPost'}
            </h1>
            <p
              className='flex min-h-6 items-center text-sm text-slate-600 sm:text-base'
              data-testid='wxpost-header-subtitle'
            >
              {headerSubtitlePending ? (
                <span
                  aria-label='Loading WxPost details'
                  className='inline-block h-4 w-40 animate-pulse rounded bg-slate-200'
                  data-testid='wxpost-header-subtitle-loading'
                />
              ) : (
                headerSubtitle
              )}
            </p>
          </div>
          <Link
            href={workspaceListPath(initialWorkspaceId)}
            className='inline-flex h-9 self-start items-center gap-1.5 whitespace-nowrap rounded-md border border-slate-300 bg-white px-4 text-sm text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 sm:self-center [&_svg]:h-4 [&_svg]:w-4'
            data-testid='wxpost-workspaces-link'
          >
            <PanelsTopLeft aria-hidden='true' />
            Workspaces
          </Link>
        </header>

        <StageTabs
          stage={stage}
          canOpenMaterials={canOpenMaterials}
          canOpenDraft={Boolean(workspaceContext?.draft)}
          onStageChange={(nextStage) => {
            setStage(nextStage);
          }}
        />

        <div hidden={stage !== 'setup'}>
          <WxPostSetupStage
            linked={linked}
            onLinkedChange={setLinked}
            meetings={meetings}
            meetingsPending={meetingsQuery.isPending}
            meetingsError={meetingsQuery.isError}
            selectedMeeting={selectedMeeting}
            meetingsLoadingMore={meetingsQuery.isFetchingNextPage}
            hasMoreMeetings={meetingsQuery.hasNextPage}
            onMeetingChange={(meetingId) => {
              const meeting =
                meetings.find((item) => item.id === meetingId) ?? null;
              if (meeting) {
                setSelectedMeeting(meeting);
                setSyncWorkspaceMeeting(false);
              }
            }}
            onLoadMoreMeetings={() => {
              void meetingsQuery.fetchNextPage();
            }}
            onRetryMeetings={() => {
              void meetingsQuery.refetch();
            }}
            onCreate={() => void handleCreateWorkspace()}
            isCreating={workspacePending}
            createError={workspaceError}
            sourceLocked={Boolean(workspaceContext)}
          />
        </div>

        <div hidden={stage !== 'materials'}>
          {workspacePending && !workspaceContext ? (
            <div
              className='grid min-h-[50vh] place-content-center'
              role='status'
              data-testid='workspace-resume-status'
            >
              <Loader2
                className='h-8 w-8 animate-spin text-blue-500'
                aria-hidden='true'
              />
              <span className='sr-only'>Loading workspace…</span>
            </div>
          ) : workspaceError && !workspaceContext ? (
            <div
              className='grid min-h-40 place-content-center text-sm text-red-700'
              role='alert'
            >
              {workspaceError}
            </div>
          ) : (
            workspaceId &&
            workspaceContext &&
            materialsWorkingCopy && (
              <WxPostMaterialsStage
                key={workspaceId}
                active={stage === 'materials'}
                workspaceId={workspaceId}
                context={workspaceContext}
                onContextChange={applyChangedWorkspaceContext}
                workingCopy={materialsWorkingCopy}
                onWorkingCopyChange={(updater) =>
                  setMaterialsWorkingCopy((current) =>
                    current ? updater(current) : current
                  )
                }
                onGenerateDraft={handleGenerateDraft}
                draftGenerationPending={draftGenerationPending}
              />
            )
          )}
        </div>

        {workspaceId && workspaceContext?.draft && (
          <div
            className='w-full min-[761px]:relative min-[761px]:left-1/2 min-[761px]:w-[min(calc(100vw_-_40px),1380px)] min-[761px]:-translate-x-1/2'
            hidden={stage !== 'draft'}
          >
            <WxPostDraftStage
              active={stage === 'draft'}
              workspaceId={workspaceId}
              context={workspaceContext}
              contextLabel={
                displayedMeeting?.no
                  ? `SoarHigh · ${displayedMeeting.no}`
                  : undefined
              }
              onContextChange={applyChangedWorkspaceContext}
              onRegenerate={handleGenerateDraft}
              regeneratePending={draftGenerationPending}
            />
          </div>
        )}
      </div>
    </div>
  );
}
