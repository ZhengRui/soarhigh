'use client';

import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import { getMeetingById } from '@/utils/meeting';
import {
  deleteWorkspace,
  listWorkspaces,
  type WorkspaceArticleType,
  type WorkspaceSummary,
} from '@/utils/wxpostWorkspace';

const ARTICLE_TYPE_LABELS: Record<WorkspaceArticleType, string> = {
  'meeting-recap': 'Meeting Recap',
  'member-story': 'Member Story',
  'event-preview': 'Event Preview',
  'meeting-review': 'Meeting Review',
  'action-guide': 'Action Guide',
  custom: 'Custom',
};

const BUTTON_CLASS =
  'inline-flex h-9 items-center justify-center gap-1.5 rounded-md border px-3 text-sm font-medium no-underline transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:h-4 [&_svg]:w-4';

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function workspaceSubject(
  workspace: WorkspaceSummary,
  meetingNumbers: Map<string, number>
) {
  const meetingNumber = workspace.meetingId
    ? meetingNumbers.get(workspace.meetingId)
    : undefined;
  if (meetingNumber !== undefined) return `Meeting #${meetingNumber}`;
  return workspace.meetingId ? 'Linked meeting' : 'Independent article';
}

function workspaceType(workspace: WorkspaceSummary) {
  if (workspace.articleType === 'custom' && workspace.customArticleType) {
    return workspace.customArticleType;
  }
  return ARTICLE_TYPE_LABELS[workspace.articleType];
}

export default function WxPostDraftsPage() {
  const queryClient = useQueryClient();
  const workspacesQuery = useQuery({
    queryKey: ['wxpost-workspaces'],
    queryFn: listWorkspaces,
  });
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceSummary | null>(
    null
  );
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const workspaces = useMemo(
    () => workspacesQuery.data?.items ?? [],
    [workspacesQuery.data?.items]
  );
  const meetingIds = useMemo(
    () =>
      Array.from(
        new Set(
          workspaces
            .map((workspace) => workspace.meetingId)
            .filter((meetingId): meetingId is string => Boolean(meetingId))
        )
      ),
    [workspaces]
  );
  const meetingQueries = useQueries({
    queries: meetingIds.map((meetingId) => ({
      queryKey: ['meeting', meetingId],
      queryFn: () => getMeetingById(meetingId),
      staleTime: 60 * 1000,
    })),
  });
  const meetingNumbers = new Map(
    meetingIds.flatMap((meetingId, index) => {
      const meetingNumber = meetingQueries[index]?.data?.no;
      return meetingNumber === undefined
        ? []
        : ([[meetingId, meetingNumber]] as const);
    })
  );

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(
        deleteTarget.workspaceId,
        deleteTarget.manifestVersion
      );
      queryClient.setQueryData<{ items: WorkspaceSummary[] }>(
        ['wxpost-workspaces'],
        (current) => ({
          items:
            current?.items.filter(
              (workspace) => workspace.workspaceId !== deleteTarget.workspaceId
            ) ?? [],
        })
      );
      setDeleteTarget(null);
    } catch (error) {
      setDeleteError(
        error instanceof Error
          ? error.message
          : 'The workspace could not be deleted.'
      );
    } finally {
      setDeletePending(false);
    }
  }

  return (
    <div className='min-h-screen bg-[#f3f6fa] text-slate-950'>
      <main
        className='mx-auto w-[min(calc(100%_-_40px),1080px)] py-[34px] pb-[72px] max-[760px]:w-[min(calc(100%_-_24px),1080px)] max-[760px]:pt-6 max-[480px]:w-[min(calc(100%_-_20px),1080px)]'
        data-testid='wxpost-page-shell'
      >
        <Link
          href='/posts/wxposts/new'
          className='mb-6 inline-flex items-center gap-2 text-sm font-semibold text-[#46556f] no-underline hover:text-[#245feb] max-[480px]:mb-[18px] [&_svg]:h-[17px] [&_svg]:w-[17px]'
        >
          <ArrowLeft aria-hidden='true' />
          Back to New WeChat Post
        </Link>

        <header className='mb-8'>
          <h1 className='mb-2 text-3xl font-bold text-slate-950 sm:mb-4 sm:text-4xl'>
            WXPost Drafts
          </h1>
          <p className='text-sm text-slate-600 sm:text-base'>
            All members can continue or delete any saved workspace.
          </p>
        </header>

        {workspacesQuery.isPending ? (
          <div
            className='grid min-h-[55vh] place-content-center justify-items-center gap-3 text-sm text-slate-500'
            role='status'
          >
            <Loader2
              className='h-8 w-8 animate-spin text-blue-500'
              aria-hidden='true'
            />
            Loading drafts…
          </div>
        ) : workspacesQuery.isError ? (
          <div
            className='flex min-h-[45vh] flex-col items-center justify-center gap-4 text-center text-sm text-red-700'
            role='alert'
          >
            <p className='m-0'>
              {workspacesQuery.error instanceof Error
                ? workspacesQuery.error.message
                : 'The draft list could not be loaded.'}
            </p>
            <button
              type='button'
              className={`${BUTTON_CLASS} border-slate-300 bg-white text-slate-700 shadow-sm hover:border-slate-400 hover:bg-slate-50`}
              onClick={() => void workspacesQuery.refetch()}
            >
              <RefreshCw aria-hidden='true' />
              Retry
            </button>
          </div>
        ) : workspaces.length === 0 ? (
          <div className='grid min-h-[45vh] place-content-center justify-items-center gap-3 text-center text-slate-500'>
            <FileText className='h-8 w-8 text-slate-400' aria-hidden='true' />
            <p className='m-0 text-sm'>No WXPost drafts yet.</p>
          </div>
        ) : (
          <div className='space-y-5' data-testid='wxpost-drafts-list'>
            {workspaces.map((workspace) => {
              const subject = workspaceSubject(workspace, meetingNumbers);
              return (
                <article
                  key={workspace.workspaceId}
                  className='grid gap-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:p-6'
                  data-testid={`workspace-${workspace.workspaceId}`}
                >
                  <div className='min-w-0'>
                    <div className='flex flex-wrap items-center gap-2'>
                      <h2 className='text-xl font-semibold text-slate-950'>
                        {subject}
                      </h2>
                      <span className='rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700'>
                        {workspaceType(workspace)}
                      </span>
                    </div>
                    <p className='mt-3 text-sm text-slate-600'>
                      Created by {workspace.createdBy.name} · Updated{' '}
                      {formatTimestamp(workspace.updatedAt)}
                    </p>
                    <p className='mt-1.5 text-xs text-slate-500'>
                      {workspace.readySourceCount} of {workspace.sourceCount}{' '}
                      materials ready · {workspace.includedSourceCount} included
                    </p>
                    <code className='mt-3 block overflow-hidden text-ellipsis whitespace-nowrap text-xs text-slate-400'>
                      {workspace.workspaceId}
                    </code>
                  </div>
                  <div className='flex items-center gap-2 sm:justify-end'>
                    <button
                      type='button'
                      className={`${BUTTON_CLASS} border-red-200 bg-white text-red-700 hover:border-red-300 hover:bg-red-50`}
                      aria-label={`Delete ${subject} ${workspaceType(workspace)}`}
                      onClick={() => {
                        setDeleteError(null);
                        setDeleteTarget(workspace);
                      }}
                    >
                      <Trash2 aria-hidden='true' />
                      Delete
                    </button>
                    <Link
                      href={`/posts/wxposts/new?workspace=${encodeURIComponent(workspace.workspaceId)}`}
                      className={`${BUTTON_CLASS} border-transparent bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-sm hover:from-blue-700 hover:to-purple-700 hover:shadow-md`}
                    >
                      Continue
                      <ArrowRight aria-hidden='true' />
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </main>

      {deleteTarget && (
        <div
          className='fixed inset-0 z-[90] grid place-items-center bg-slate-950/50 p-4'
          role='dialog'
          aria-modal='true'
          aria-labelledby='delete-workspace-title'
          data-testid='delete-workspace-dialog'
        >
          <div className='w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-xl'>
            <h2
              id='delete-workspace-title'
              className='text-lg font-semibold text-slate-950'
            >
              Delete {workspaceSubject(deleteTarget, meetingNumbers)} draft?
            </h2>
            <p className='mb-0 mt-3 text-sm leading-6 text-slate-600'>
              This permanently removes its workspace files for every member.
            </p>
            {deleteError && (
              <p className='mb-0 mt-3 text-sm text-red-700' role='alert'>
                {deleteError}
              </p>
            )}
            <div className='mt-5 flex justify-end gap-2'>
              <button
                type='button'
                className={`${BUTTON_CLASS} border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50`}
                disabled={deletePending}
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type='button'
                className={`${BUTTON_CLASS} border-red-700 bg-red-700 text-white hover:bg-red-800`}
                disabled={deletePending}
                onClick={() => void confirmDelete()}
              >
                {deletePending ? (
                  <Loader2 className='animate-spin' aria-hidden='true' />
                ) : (
                  <Trash2 aria-hidden='true' />
                )}
                Delete draft
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
