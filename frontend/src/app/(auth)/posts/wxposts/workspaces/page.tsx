'use client';

import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import {
  ArrowLeft,
  BookOpenText,
  CircleCheck,
  Clock3,
  ExternalLink,
  FileText,
  Globe2,
  Images,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { Pagination } from '@/components/Pagination';
import { getMeetingOptionsByIds } from '@/utils/meeting';
import {
  WORKSPACE_ARTICLE_TYPE_LABELS,
  WorkspaceApiError,
  deleteWorkspace,
  listWorkspaces,
  workspaceDraftPreviewPath,
  workspaceEditorPath,
  workspaceIdFromEditorKey,
  type WorkspaceSummary,
} from '@/utils/wxpostWorkspace';

const WORKSPACE_PAGE_SIZE = 10;
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
  meetings: Map<string, { no?: number; theme: string }>
) {
  const meeting = workspace.meetingId
    ? meetings.get(workspace.meetingId)
    : undefined;
  const theme = meeting?.theme.trim();
  if (theme) return theme;
  if (meeting?.no !== undefined) return `Meeting #${meeting.no}`;
  return workspace.meetingId ? 'Linked meeting' : 'Independent article';
}

function workspaceReference(
  workspace: WorkspaceSummary,
  meetings: Map<string, { no?: number }>
) {
  if (!workspace.meetingId) return null;
  const meetingNumber = meetings.get(workspace.meetingId)?.no;
  return meetingNumber === undefined ? null : `#${meetingNumber}`;
}

function workspaceType(workspace: WorkspaceSummary) {
  if (workspace.articleType === 'custom' && workspace.customArticleType) {
    return workspace.customArticleType;
  }
  return WORKSPACE_ARTICLE_TYPE_LABELS[workspace.articleType];
}

function workspacePublicationLabel(workspace: WorkspaceSummary) {
  const publication = workspace.publication;
  if (publication.state === 'unavailable') return 'Public status unavailable';
  if (publication.state === 'not-synced') return 'Not published';
  if (
    publication.publicRevision === null ||
    publication.sourceDraftVersion === null
  ) {
    return 'Public status unavailable';
  }

  const published = `Public revision ${publication.publicRevision} · from Draft v${publication.sourceDraftVersion}`;
  return publication.state === 'update-available' &&
    workspace.draftVersion !== null
    ? `${published} · Draft v${workspace.draftVersion} ready to publish`
    : published;
}

export default function WxPostWorkspacesPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const returnWorkspaceKey =
    searchParams.get('from') === 'edit' ? searchParams.get('workspace') : null;
  const cameFromNew = searchParams.get('from') === 'new';
  const backHref = returnWorkspaceKey
    ? workspaceEditorPath(workspaceIdFromEditorKey(returnWorkspaceKey))
    : cameFromNew
      ? '/posts/wxposts/new'
      : '/posts';
  const backLabel = returnWorkspaceKey
    ? 'Back to WxPost'
    : cameFromNew
      ? 'Back to New WxPost'
      : 'Back to Posts';
  const [currentPage, setCurrentPage] = useState(1);
  const workspacesQuery = useQuery({
    queryKey: [
      'wxpost-workspaces',
      { page: currentPage, pageSize: WORKSPACE_PAGE_SIZE },
    ],
    queryFn: () =>
      listWorkspaces({
        page: currentPage,
        pageSize: WORKSPACE_PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
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
  const meetingOptionsQuery = useQuery({
    queryKey: ['meeting-options-by-ids', meetingIds],
    queryFn: () => getMeetingOptionsByIds(meetingIds),
    enabled: meetingIds.length > 0,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: 60 * 1000,
  });
  const meetingsById = new Map(
    (meetingOptionsQuery.data?.items ?? []).map(
      (meeting) =>
        [meeting.id, { no: meeting.no, theme: meeting.theme }] as const
    )
  );
  const meetingMetadataPending =
    meetingIds.length > 0 && meetingOptionsQuery.isPending;
  const workspacesRefreshing =
    !workspacesQuery.isPending &&
    !meetingMetadataPending &&
    (workspacesQuery.isFetching || meetingOptionsQuery.isFetching);
  const totalPages = workspacesQuery.data?.pages ?? 1;

  useEffect(() => {
    if (workspacesQuery.data && currentPage > workspacesQuery.data.pages) {
      setCurrentPage(Math.max(1, workspacesQuery.data.pages));
    }
  }, [currentPage, workspacesQuery.data]);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(
        deleteTarget.workspaceId,
        deleteTarget.manifestVersion
      );
      setDeleteTarget(null);
      await queryClient.invalidateQueries({
        queryKey: ['wxpost-workspaces'],
        refetchType: 'none',
      });
      if (workspaces.length === 1 && currentPage > 1) {
        setCurrentPage((page) => page - 1);
      } else {
        await workspacesQuery.refetch();
      }
    } catch (error) {
      if (
        error instanceof WorkspaceApiError &&
        (error.code === 'version_conflict' ||
          error.code === 'workspace_not_found')
      ) {
        setDeleteTarget(null);
        await workspacesQuery.refetch();
        return;
      }
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
          href={backHref}
          className='mb-6 inline-flex items-center gap-2 text-sm font-semibold text-[#46556f] no-underline hover:text-[#245feb] max-[480px]:mb-[18px] [&_svg]:h-[17px] [&_svg]:w-[17px]'
        >
          <ArrowLeft aria-hidden='true' />
          {backLabel}
        </Link>

        <header className='mb-8'>
          <h1 className='mb-2 text-3xl font-bold text-slate-950 sm:mb-4 sm:text-4xl'>
            Workspaces
          </h1>
          <p className='text-sm text-slate-600 sm:text-base'>
            Each workspace contains the materials and drafts for one WxPost.
          </p>
        </header>

        {workspacesQuery.isPending || meetingMetadataPending ? (
          <div
            className='flex min-h-[70vh] flex-col items-center justify-center py-12'
            role='status'
            data-testid='workspaces-loading'
          >
            <Loader2
              className='mb-4 h-8 w-8 animate-spin text-blue-500'
              aria-hidden='true'
            />
            <span className='sr-only'>Loading workspaces…</span>
          </div>
        ) : workspacesQuery.isError && !workspacesQuery.data ? (
          <div
            className='flex min-h-[45vh] flex-col items-center justify-center gap-4 text-center text-sm text-red-700'
            role='alert'
          >
            <p className='m-0'>
              {workspacesQuery.error instanceof Error
                ? workspacesQuery.error.message
                : 'The workspace list could not be loaded.'}
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
            <p className='m-0 text-sm'>No WxPost workspaces yet.</p>
          </div>
        ) : (
          <>
            {workspacesRefreshing && (
              <div
                className='mb-4 flex items-center justify-center gap-2 rounded-md bg-blue-50 px-4 py-2 text-sm text-blue-600'
                data-testid='workspaces-refreshing'
              >
                <RefreshCw
                  className='h-4 w-4 animate-spin'
                  aria-hidden='true'
                />
                Refreshing workspaces…
              </div>
            )}
            {meetingOptionsQuery.isError && (
              <div
                className='mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900'
                role='alert'
                data-testid='meeting-metadata-warning'
              >
                <span>
                  Meeting details are temporarily unavailable. Linked workspaces
                  are still available.
                </span>
                <button
                  type='button'
                  className='inline-flex items-center gap-2 font-bold hover:underline [&_svg]:h-4 [&_svg]:w-4'
                  onClick={() => void meetingOptionsQuery.refetch()}
                >
                  <RefreshCw aria-hidden='true' />
                  Retry meeting details
                </button>
              </div>
            )}
            <div className='space-y-5' data-testid='wxpost-workspaces-list'>
              {workspaces.map((workspace) => {
                const subject = workspaceSubject(workspace, meetingsById);
                const reference = workspaceReference(workspace, meetingsById);
                return (
                  <article
                    key={workspace.workspaceId}
                    className='relative overflow-hidden rounded-xl border border-slate-200 bg-white p-5 shadow-lg transition-all duration-200 ease-in-out hover:shadow-xl sm:p-6'
                    data-testid={`workspace-${workspace.workspaceId}`}
                  >
                    <button
                      type='button'
                      className='absolute right-5 top-5 z-10 grid h-8 w-8 place-items-center rounded-full bg-red-50 text-red-400 transition hover:bg-red-100 hover:text-red-600 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 sm:right-6 sm:top-6 [&_svg]:h-4 [&_svg]:w-4'
                      aria-label={`Delete ${subject} ${workspaceType(workspace)}`}
                      title='Delete workspace'
                      onClick={() => {
                        setDeleteError(null);
                        setDeleteTarget(workspace);
                      }}
                    >
                      <Trash2 aria-hidden='true' />
                    </button>

                    <div className='pr-12'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <span className='rounded-full bg-gradient-to-r from-blue-600 to-purple-600 px-4 py-1 text-sm font-medium text-white'>
                          {workspace.meetingId ? 'Linked' : 'Independent'}
                        </span>
                        {reference && (
                          <span className='rounded-full bg-fuchsia-50 px-2 py-1.5 text-xs font-medium text-fuchsia-500'>
                            {reference}
                          </span>
                        )}
                        <Link
                          href={workspaceEditorPath(workspace.workspaceId)}
                          className='rounded-full bg-indigo-50 p-1.5 transition hover:bg-indigo-100 hover:shadow-md'
                          aria-label='Go to Materials'
                          title='Go to Materials'
                        >
                          <Images
                            className='h-4 w-4 text-indigo-500 hover:text-indigo-600'
                            aria-hidden='true'
                          />
                        </Link>
                        {workspace.draftVersion !== null && (
                          <Link
                            href={workspaceDraftPreviewPath(
                              workspace.workspaceId
                            )}
                            className='rounded-full bg-indigo-50 p-1.5 transition hover:bg-indigo-100 hover:shadow-md'
                            aria-label='Go to Draft'
                            title='Go to Draft'
                          >
                            <BookOpenText
                              className='h-4 w-4 text-indigo-500 hover:text-indigo-600'
                              aria-hidden='true'
                            />
                          </Link>
                        )}
                      </div>
                      <h2 className='mt-3 text-2xl font-bold text-slate-800'>
                        {subject}
                      </h2>
                      <p className='mb-0 mt-1 text-sm text-slate-500'>
                        Created by {workspace.createdBy.name}
                      </p>
                    </div>

                    <div className='mt-4 flex flex-col gap-2 text-sm text-slate-500'>
                      <span className='inline-flex items-center gap-2'>
                        <FileText
                          className='h-4 w-4 shrink-0'
                          aria-hidden='true'
                        />
                        Article type · {workspaceType(workspace)}
                      </span>
                      <span className='inline-flex items-center gap-2'>
                        <Clock3
                          className='h-4 w-4 shrink-0'
                          aria-hidden='true'
                        />
                        Updated {formatTimestamp(workspace.updatedAt)}
                      </span>
                      <span className='inline-flex items-center gap-2'>
                        <Images
                          className='h-4 w-4 shrink-0'
                          aria-hidden='true'
                        />
                        {workspace.readySourceCount} of {workspace.sourceCount}{' '}
                        materials ready · {workspace.includedSourceCount}{' '}
                        included
                      </span>
                    </div>

                    <div className='mt-5 grid gap-2 border-t border-dashed border-slate-300 pt-4 sm:flex sm:items-center sm:justify-between'>
                      <span
                        className={`inline-flex items-center gap-2 text-sm font-medium ${
                          workspace.draftVersion !== null
                            ? 'text-slate-700'
                            : 'text-slate-500'
                        }`}
                      >
                        {workspace.draftVersion !== null ? (
                          <CircleCheck
                            className='h-4 w-4 text-blue-600'
                            aria-hidden='true'
                          />
                        ) : (
                          <FileText
                            className='h-4 w-4 text-slate-400'
                            aria-hidden='true'
                          />
                        )}
                        {workspace.draftVersion !== null
                          ? `Draft · v${workspace.draftVersion}`
                          : 'No draft yet'}
                      </span>
                      <span className='inline-flex items-center gap-2 text-sm font-medium text-slate-500'>
                        <Globe2
                          className={`h-4 w-4 ${
                            workspace.publication.state === 'up-to-date'
                              ? 'text-blue-600'
                              : 'text-slate-400'
                          }`}
                          aria-hidden='true'
                        />
                        {workspacePublicationLabel(workspace)}
                        {workspace.publication.publicUrl && (
                          <a
                            href={workspace.publication.publicUrl}
                            target='_blank'
                            rel='noreferrer'
                            className='rounded-full p-1 text-blue-600 transition hover:bg-blue-50 hover:text-blue-700'
                            aria-label={`Open public WxPost for ${subject}`}
                            title='Open public WxPost'
                          >
                            <ExternalLink
                              className='h-3.5 w-3.5'
                              aria-hidden='true'
                            />
                          </a>
                        )}
                      </span>
                    </div>
                  </article>
                );
              })}
            </div>
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={(page) => {
                setCurrentPage(page);
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
            />
            {workspacesQuery.data.total > 0 && (
              <div className='mt-4 text-center text-sm text-slate-500'>
                Showing{' '}
                {Math.min(
                  (currentPage - 1) * WORKSPACE_PAGE_SIZE + 1,
                  workspacesQuery.data.total
                )}{' '}
                to{' '}
                {Math.min(
                  currentPage * WORKSPACE_PAGE_SIZE,
                  workspacesQuery.data.total
                )}{' '}
                of {workspacesQuery.data.total} workspaces
              </div>
            )}
          </>
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
              Delete {workspaceSubject(deleteTarget, meetingsById)} workspace?
            </h2>
            <p className='mb-0 mt-3 text-sm leading-6 text-slate-600'>
              This permanently removes its workspace files for every member. Any
              already published WxPost and its public assets will remain
              available.
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
                Delete workspace
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
