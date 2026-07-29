'use client';

import { ArrowLeft, Check, FileText } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { useMeetingOptions } from '@/hooks/useMeetingOptions';
import {
  bootstrapWorkspace,
  getWorkspaceContext,
  updateWorkspace,
  type WorkspaceArticleType,
  type WorkspaceContext,
  type WorkspaceEditorial,
} from '@/utils/wxpostWorkspace';

import type { WxPostArticleType, WxPostAuthoringStage } from './types';
import {
  formatMeetingLabel,
  type LinkedMeetingOption,
  WxPostSetupStage,
} from './WxPostSetupStage';
import { WxPostMaterialsStage } from './WxPostMaterialsStage';
import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
  STAGE_BUTTON_CLASS,
} from './authoringStyles';

const ARTICLE_TYPE_TO_WIRE: Record<WxPostArticleType, WorkspaceArticleType> = {
  'Meeting Recap': 'meeting-recap',
  'Member Story': 'member-story',
  'Event Preview': 'event-preview',
  'Meeting Review': 'meeting-review',
  'Action Guide': 'action-guide',
  Custom: 'custom',
};
const ARTICLE_TYPE_FROM_WIRE = Object.fromEntries(
  Object.entries(ARTICLE_TYPE_TO_WIRE).map(([label, value]) => [value, label])
) as Record<WorkspaceArticleType, WxPostArticleType>;

type PendingSourceChange =
  | { kind: 'meeting'; meeting: LinkedMeetingOption }
  | { kind: 'independent' };

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
      aria-label='WXPost creation progress'
    >
      <button
        type='button'
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

export function WxPostAuthoringWorkspace() {
  const [stage, setStage] = useState<WxPostAuthoringStage>('setup');
  const [articleType, setArticleType] =
    useState<WxPostArticleType>('Meeting Recap');
  const [customArticleType, setCustomArticleType] = useState('');
  const [linked, setLinked] = useState(true);
  const [selectedMeeting, setSelectedMeeting] =
    useState<LinkedMeetingOption | null>(null);
  const [pendingSourceChange, setPendingSourceChange] =
    useState<PendingSourceChange | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspaceContext, setWorkspaceContext] =
    useState<WorkspaceContext | null>(null);
  const [workspacePending, setWorkspacePending] = useState(false);
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

  const applyWorkspaceContext = useCallback((context: WorkspaceContext) => {
    setWorkspaceId(context.workspaceId);
    setWorkspaceContext(context);
    setArticleType(
      ARTICLE_TYPE_FROM_WIRE[context.manifest.editorial.articleType]
    );
    setCustomArticleType(context.manifest.editorial.customArticleType ?? '');
    setLinked(Boolean(context.manifest.meetingId));
    setSelectedMeeting((current) =>
      current?.id === context.manifest.meetingId ? current : null
    );
    setSyncWorkspaceMeeting(Boolean(context.manifest.meetingId));
  }, []);

  useEffect(() => {
    const resumedWorkspaceId = new URLSearchParams(window.location.search).get(
      'workspace'
    );
    if (!resumedWorkspaceId) return;

    let active = true;
    setWorkspacePending(true);
    void getWorkspaceContext(resumedWorkspaceId)
      .then((context) => {
        if (!active) return;
        applyWorkspaceContext(context);
        setStage('materials');
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
  }, [applyWorkspaceContext]);

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

  const handleContinue = useCallback(async () => {
    const meetingId = linked ? (selectedMeeting?.id ?? null) : null;
    if (linked && !meetingId) return;
    const editorial: WorkspaceEditorial = {
      ...(workspaceContext?.manifest.editorial ?? {
        writingApproach: 'chronological',
        transcript: '',
        extraNotes: '',
        writingGuidance: '',
      }),
      articleType: ARTICLE_TYPE_TO_WIRE[articleType],
      customArticleType:
        articleType === 'Custom' ? customArticleType.trim() || null : null,
    };

    const current = workspaceContext?.manifest;
    const settingsChanged =
      current?.meetingId !== meetingId ||
      current.editorial.articleType !== editorial.articleType ||
      current.editorial.customArticleType !== editorial.customArticleType;
    const nextWorkspaceId = workspaceId ?? createWorkspaceId();

    setWorkspacePending(true);
    setWorkspaceError(null);
    try {
      const context =
        current && workspaceId && settingsChanged
          ? await updateWorkspace(workspaceId, {
              expectedManifestVersion: current.manifestVersion,
              meetingId,
              editorial,
            })
          : await bootstrapWorkspace(nextWorkspaceId, {
              meetingId,
              editorial,
            });
      applyWorkspaceContext(context);
      const url = new URL(window.location.href);
      url.searchParams.set('workspace', context.workspaceId);
      window.history.replaceState(null, '', url);
      setStage('materials');
    } catch (error) {
      setWorkspaceError(
        error instanceof Error
          ? error.message
          : 'Unable to create the material workspace.'
      );
    } finally {
      setWorkspacePending(false);
    }
  }, [
    applyWorkspaceContext,
    articleType,
    customArticleType,
    linked,
    selectedMeeting,
    workspaceContext?.manifest,
    workspaceId,
  ]);

  const effectiveMeeting = linked ? selectedMeeting : null;
  const canOpenMaterials = Boolean(workspaceContext);
  const workspaceMeeting =
    workspaceContext?.manifest.meetingId &&
    selectedMeeting?.id === workspaceContext.manifest.meetingId
      ? selectedMeeting
      : null;
  const displayedMeeting =
    stage === 'materials' ? workspaceMeeting : effectiveMeeting;
  const displayedArticleType =
    stage === 'materials' && workspaceContext
      ? ARTICLE_TYPE_FROM_WIRE[workspaceContext.manifest.editorial.articleType]
      : articleType;

  function openExistingMaterials() {
    if (!workspaceContext) return;
    applyWorkspaceContext(workspaceContext);
    setStage('materials');
  }

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
              New WeChat Post
            </h1>
            <p className='text-sm text-slate-600 sm:text-base'>
              {displayedMeeting
                ? `${formatMeetingLabel(displayedMeeting)} · ${displayedArticleType}`
                : workspaceContext?.manifest.meetingId && linked
                  ? `Linked meeting · ${displayedArticleType}`
                  : `Independent article · ${displayedArticleType}`}
            </p>
          </div>
          <Link
            href='/posts/wxposts/drafts'
            className='inline-flex h-9 self-start items-center gap-1.5 whitespace-nowrap rounded-md border border-slate-300 bg-white px-4 text-sm text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 sm:self-center [&_svg]:h-4 [&_svg]:w-4'
            data-testid='wxpost-drafts-link'
          >
            <FileText aria-hidden='true' />
            WXPost Drafts
          </Link>
        </header>

        <StageTabs
          stage={stage}
          canOpenMaterials={canOpenMaterials}
          onStageChange={(nextStage) => {
            if (nextStage === 'materials') openExistingMaterials();
            else setStage(nextStage);
          }}
        />

        <div hidden={stage !== 'setup'}>
          <WxPostSetupStage
            articleType={articleType}
            onArticleTypeChange={setArticleType}
            customArticleType={customArticleType}
            onCustomArticleTypeChange={setCustomArticleType}
            linked={linked}
            onLinkedChange={(nextLinked) => {
              if (!nextLinked && workspaceContext?.manifest.meetingId) {
                setPendingSourceChange({ kind: 'independent' });
                return;
              }
              setLinked(nextLinked);
            }}
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
                const currentMeetingId =
                  workspaceContext?.manifest.meetingId ?? null;
                if (currentMeetingId && currentMeetingId !== meeting.id) {
                  setPendingSourceChange({ kind: 'meeting', meeting });
                  return;
                }
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
            onContinue={() => void handleContinue()}
            isContinuing={workspacePending}
            continueError={workspaceError}
          />
        </div>

        <div hidden={stage !== 'materials'}>
          {workspaceId && workspaceContext && (
            <WxPostMaterialsStage
              key={workspaceId}
              active={stage === 'materials'}
              workspaceId={workspaceId}
              context={workspaceContext}
              onContextChange={setWorkspaceContext}
              onBack={() => setStage('setup')}
            />
          )}
        </div>

        {pendingSourceChange && (
          <div
            className='fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4'
            role='dialog'
            aria-modal='true'
            aria-labelledby='change-meeting-title'
            data-testid='change-meeting-dialog'
          >
            <div className='w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl'>
              <h2
                id='change-meeting-title'
                className='m-0 text-lg font-bold text-slate-900'
              >
                {pendingSourceChange.kind === 'meeting'
                  ? 'Change meeting?'
                  : 'Make this article independent?'}
              </h2>
              <p className='mb-0 mt-3 text-sm leading-6 text-slate-600'>
                Materials imported from{' '}
                <strong className='font-semibold text-slate-800'>
                  {selectedMeeting
                    ? formatMeetingLabel(selectedMeeting)
                    : 'the current meeting'}
                </strong>{' '}
                will be removed
                {pendingSourceChange.kind === 'meeting' && (
                  <>
                    {' '}
                    and replaced with materials from{' '}
                    <strong className='font-semibold text-slate-800'>
                      {formatMeetingLabel(pendingSourceChange.meeting)}
                    </strong>
                  </>
                )}
                . Files you uploaded yourself will be kept.
              </p>
              <div className='mt-5 flex justify-end gap-2'>
                <button
                  type='button'
                  className={SECONDARY_BUTTON_CLASS}
                  onClick={() => setPendingSourceChange(null)}
                >
                  Cancel
                </button>
                <button
                  type='button'
                  className={PRIMARY_BUTTON_CLASS}
                  onClick={() => {
                    if (pendingSourceChange.kind === 'meeting') {
                      setSelectedMeeting(pendingSourceChange.meeting);
                      setLinked(true);
                    } else {
                      setLinked(false);
                    }
                    setSyncWorkspaceMeeting(false);
                    setPendingSourceChange(null);
                  }}
                >
                  {pendingSourceChange.kind === 'meeting'
                    ? 'Change meeting'
                    : 'Make independent'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
