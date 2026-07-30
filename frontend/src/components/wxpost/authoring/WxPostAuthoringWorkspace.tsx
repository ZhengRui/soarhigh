'use client';

import { ArrowLeft, Check, Loader2, PanelsTopLeft } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { useMeetingOptions } from '@/hooks/useMeetingOptions';
import {
  bootstrapWorkspace,
  getWorkspaceContext,
  WORKSPACE_ARTICLE_TYPE_LABELS,
  workspaceEditorPath,
  workspaceListPath,
  type WorkspaceContext,
  type WorkspaceEditorial,
} from '@/utils/wxpostWorkspace';

import type { WxPostAuthoringStage, WxPostMaterialsWorkingCopy } from './types';
import {
  formatMeetingLabel,
  type LinkedMeetingOption,
  WxPostSetupStage,
} from './WxPostSetupStage';
import { WxPostMaterialsStage } from './WxPostMaterialsStage';
import { STAGE_BUTTON_CLASS } from './authoringStyles';

function createInitialEditorial(
  linked: boolean,
  meeting: LinkedMeetingOption | null
): WorkspaceEditorial {
  const isEvent =
    linked &&
    meeting?.no !== undefined &&
    String(meeting.no).startsWith('10000');

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
  onStageChange,
}: {
  stage: WxPostAuthoringStage;
  canOpenMaterials: boolean;
  onStageChange: (stage: WxPostAuthoringStage) => void;
}) {
  const activeClass =
    'bg-[#eff5ff] text-blue-700 after:absolute after:bottom-0 after:left-[18px] after:right-[18px] after:h-0.5 after:rounded-t-full after:bg-blue-600 [&>span]:bg-blue-600 [&>span]:text-white';

  return (
    <nav
      className='mb-6 grid grid-cols-4 overflow-hidden rounded-[14px] border border-[#d9e1ec] bg-white max-[480px]:rounded-xl'
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
        <span>{stage === 'materials' ? <Check /> : '1'}</span>
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
        <span>2</span>
        Materials
      </button>
      <button
        type='button'
        className={`${STAGE_BUTTON_CLASS} cursor-default text-[#a2adbd]`}
        disabled
      >
        <span>3</span>
        Draft
      </button>
      <button
        type='button'
        className={`${STAGE_BUTTON_CLASS} cursor-default text-[#a2adbd]`}
        disabled
      >
        <span>4</span>
        Preview
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
  const meetingsQuery = useMeetingOptions();

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
      setWorkspaceContext(context);
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

  const effectiveMeeting = linked ? selectedMeeting : null;
  const canOpenMaterials = Boolean(initialWorkspaceId || workspaceContext);
  const workspaceMeeting =
    workspaceContext?.manifest.meetingId &&
    selectedMeeting?.id === workspaceContext.manifest.meetingId
      ? selectedMeeting
      : null;
  const displayedMeeting =
    stage === 'materials' ? workspaceMeeting : effectiveMeeting;
  const displayedArticleType =
    stage === 'materials' ? materialsWorkingCopy?.articleType : null;
  const displayedArticleTypeLabel = displayedArticleType
    ? WORKSPACE_ARTICLE_TYPE_LABELS[displayedArticleType]
    : null;

  return (
    <div className='min-h-screen bg-[#f3f6fa] text-base text-[#172033]'>
      <div
        className='mx-auto w-[min(calc(100%_-_40px),1080px)] py-[34px] pb-[72px] max-[760px]:w-[min(calc(100%_-_24px),1080px)] max-[760px]:pt-6 max-[480px]:w-[min(calc(100%_-_20px),1080px)]'
        data-testid='wxpost-page-shell'
      >
        <Link
          href='/posts'
          className='mb-6 inline-flex items-center gap-2 text-sm font-semibold text-[#46556f] no-underline hover:text-[#245feb] max-[480px]:mb-[18px] [&_svg]:h-[17px] [&_svg]:w-[17px]'
        >
          <ArrowLeft aria-hidden='true' />
          Back to Posts
        </Link>

        <header className='mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between'>
          <div>
            <h1 className='mb-2 text-3xl font-bold text-slate-950 sm:mb-4 sm:text-4xl'>
              {initialWorkspaceId ? 'WxPost' : 'New WxPost'}
            </h1>
            <p className='text-sm text-slate-600 sm:text-base'>
              {displayedMeeting
                ? `${formatMeetingLabel(displayedMeeting)}${
                    displayedArticleTypeLabel
                      ? ` · ${displayedArticleTypeLabel}`
                      : ''
                  }`
                : workspaceContext?.manifest.meetingId && linked
                  ? `Linked meeting${
                      displayedArticleTypeLabel
                        ? ` · ${displayedArticleTypeLabel}`
                        : ''
                    }`
                  : `Independent article${
                      displayedArticleTypeLabel
                        ? ` · ${displayedArticleTypeLabel}`
                        : ''
                    }`}
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
              />
            )
          )}
        </div>
      </div>
    </div>
  );
}
