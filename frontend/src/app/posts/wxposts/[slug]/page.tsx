'use client';

import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CalendarDays, Eye, Loader2, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';

import { ConfirmActionDialog } from '@/components/ConfirmActionDialog';
import {
  WxPostPresentationControls,
  type WxPostPresentationSelection,
  type WxPostRenderMode,
} from '@/components/wxpost/WxPostPresentationControls';
import { WxPostPresentationDrawer } from '@/components/wxpost/WxPostPresentationDrawer';
import { WxPostRenderer } from '@/components/wxpost/WxPostRenderer';
import { compileWxPost } from '@/components/wxpost/renderer/compiler';
import { formatWxPostDisplayDate } from '@/components/wxpost/renderer/context';
import { compileWxPostForWechat } from '@/components/wxpost/renderer/wechatMiniEmitter';
import type {
  WxPostPresentation,
  WxPostPublicDetail,
  WxPostWechatDraftStatus,
} from '@/components/wxpost/types';
import { useAuth } from '@/hooks/useAuth';
import { useWxPost } from '@/hooks/useWxPost';
import {
  deletePublicWxPost,
  getWxPostWechatDraft,
  getWxPostWechatPreview,
  publishWxPostWechatDraft,
  resetUncertainWxPostWechatDraft,
} from '@/utils/wxposts';

function WechatIcon() {
  return (
    <svg
      viewBox='0 0 24 24'
      className='h-5 w-5'
      fill='none'
      stroke='currentColor'
      strokeWidth='1.8'
      strokeLinecap='round'
      strokeLinejoin='round'
      aria-hidden='true'
    >
      <path d='M12.9 15.6c-1 .45-2.2.7-3.5.7C5.3 16.3 2 13.6 2 10.2s3.3-6.1 7.4-6.1 7.4 2.7 7.4 6.1c0 .2-.01.39-.04.58' />
      <path d='m5.2 14.7-.8 2.3 2.65-1.28' />
      <path d='M22 14.5c0-2.7-2.7-4.9-6-4.9s-6 2.2-6 4.9 2.7 4.9 6 4.9c.85 0 1.67-.14 2.4-.39L20.6 20l-.62-1.97C21.24 17.14 22 15.88 22 14.5Z' />
      <path d='M7 9h.01M11.8 9h.01M14.1 13.7h.01M18 13.7h.01' />
    </svg>
  );
}

function apiErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = error.message;
    if (typeof message === 'string') return message;
  }
  return fallback;
}

function PublicWxPost({
  detail,
  canDelete,
}: {
  detail: WxPostPublicDetail;
  canDelete: boolean;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const defaultSelection: WxPostPresentationSelection = {
    ...detail.render_document.presentation,
    previewSize: 'mobile-390',
  };
  const [selection, setSelection] =
    useState<WxPostPresentationSelection>(defaultSelection);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [wechatOpen, setWechatOpen] = useState(false);
  const [wechatPending, setWechatPending] = useState(false);
  const [wechatPreviewPending, setWechatPreviewPending] = useState(false);
  const [wechatError, setWechatError] = useState<string | null>(null);
  const [wechatResetConfirming, setWechatResetConfirming] = useState(false);
  const [wechatResetPending, setWechatResetPending] = useState(false);
  const [wechatResetError, setWechatResetError] = useState<string | null>(null);
  const [wechatStatus, setWechatStatus] =
    useState<WxPostWechatDraftStatus | null>(null);
  const [wechatPresentation, setWechatPresentation] =
    useState<WxPostPresentation | null>(null);

  const [renderMode, setRenderMode] = useState<WxPostRenderMode>('canonical');
  const selectedPresentation: WxPostPresentation = useMemo(
    () => ({
      layout: selection.layout,
      palette: selection.palette,
      appearance: selection.appearance,
      typeface: selection.typeface,
    }),
    [
      selection.layout,
      selection.palette,
      selection.appearance,
      selection.typeface,
    ]
  );
  const previewContext = useMemo(
    () => ({
      displayDate: formatWxPostDisplayDate(detail.created_at),
      publisherName: 'SoarHigh Toastmasters',
    }),
    [detail.created_at]
  );
  // Both exports are compiled here so the counts shown on the toggle and the
  // preview itself share one source; each is a cheap memoized string build.
  const canonicalHtml = useMemo(
    () =>
      compileWxPost({
        renderDocument: detail.render_document,
        presentation: selectedPresentation,
        context: previewContext,
      }).html,
    [detail.render_document, selectedPresentation, previewContext]
  );
  const miniHtml = useMemo(
    () =>
      compileWxPostForWechat({
        renderDocument: detail.render_document,
        presentation: selectedPresentation,
        context: previewContext,
      }).html,
    [detail.render_document, selectedPresentation, previewContext]
  );
  const charCounts = { canonical: canonicalHtml.length, mini: miniHtml.length };
  const hasVideo = detail.render_document.body.some(
    (node) => node.kind === 'directive' && node.name === 'video'
  );
  const publishPresentation = wechatPresentation ?? selectedPresentation;

  useEffect(() => {
    if (!canDelete) return;
    let cancelled = false;
    void getWxPostWechatDraft(detail.id)
      .then((status) => {
        if (!cancelled) setWechatStatus((current) => current ?? status);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [canDelete, detail.id]);

  function openWechatDialog() {
    setWechatOpen(true);
    setWechatError(null);
    setWechatPresentation(
      wechatStatus?.state === 'uncertain' && wechatStatus.presentation
        ? wechatStatus.presentation
        : selectedPresentation
    );
  }

  async function openWechatPreview() {
    setWechatPreviewPending(true);
    try {
      const previewUrl = (await getWxPostWechatPreview(detail.id)).previewUrl;
      window.open(previewUrl, '_blank', 'noopener,noreferrer');
    } catch (error) {
      const message = apiErrorMessage(
        error,
        'The official WeChat preview could not be opened.'
      );
      toast.error(message);
    } finally {
      setWechatPreviewPending(false);
    }
  }

  async function confirmWechat() {
    if (hasVideo) {
      setWechatError(
        'This Revision contains a Video block, which is not supported in Phase 3.'
      );
      return;
    }
    setWechatPending(true);
    setWechatError(null);
    try {
      const result = await publishWxPostWechatDraft(
        detail.id,
        detail.article_revision,
        publishPresentation
      );
      setWechatStatus(result);
      setWechatOpen(false);
      toast.success(
        {
          created: 'WeChat draft created!',
          updated: 'WeChat draft updated!',
          unchanged: 'WeChat draft is already up to date!',
        }[result.action]
      );
    } catch (error) {
      setWechatError(
        apiErrorMessage(error, 'The WeChat draft could not be published.')
      );
    } finally {
      setWechatPending(false);
    }
  }

  async function confirmWechatReset() {
    setWechatResetPending(true);
    setWechatResetError(null);
    try {
      const status = await resetUncertainWxPostWechatDraft(
        detail.id,
        detail.article_revision
      );
      setWechatStatus(status);
      setWechatResetConfirming(false);
      toast.success('The uncertain WeChat operation was reset.');
    } catch (error) {
      setWechatResetError(
        apiErrorMessage(
          error,
          'The uncertain WeChat operation could not be reset.'
        )
      );
    } finally {
      setWechatResetPending(false);
    }
  }

  async function confirmDelete() {
    setDeletePending(true);
    setDeleteError(null);
    try {
      await deletePublicWxPost(detail.id, detail.article_revision);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['posts'] }),
        queryClient.invalidateQueries({
          queryKey: ['wxpost-workspaces'],
          refetchType: 'none',
        }),
      ]);
      toast.success('Public WxPost deleted successfully!');
      router.replace('/posts');
    } catch (error) {
      const apiMessage =
        error &&
        typeof error === 'object' &&
        'error' in error &&
        error.error &&
        typeof error.error === 'object' &&
        'message' in error.error &&
        typeof error.error.message === 'string'
          ? error.error.message
          : null;
      setDeleteError(
        error instanceof Error
          ? error.message
          : typeof error === 'string'
            ? error
            : (apiMessage ?? 'The public WxPost could not be deleted.')
      );
    } finally {
      setDeletePending(false);
    }
  }

  return (
    <>
      <div className='relative mb-7' data-testid='public-wxpost-header'>
        <div className='min-w-0'>
          {/* Only the badge row aligns with the floating action buttons, so it
              alone reserves clearance — the title keeps full width. */}
          <div
            className={`mb-3 flex flex-wrap items-center gap-2 ${
              canDelete ? 'pr-36' : ''
            }`}
          >
            <span className='rounded-full bg-gradient-to-r from-blue-600 to-purple-600 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-white'>
              WxPost
            </span>
            <span
              className='min-w-0 break-words text-xs font-medium uppercase tracking-[0.12em] text-slate-500'
              data-testid='public-wxpost-context'
            >
              {detail.context_label}
            </span>
          </div>
          <p
            className='max-w-3xl break-words text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl'
            data-testid='public-wxpost-title'
          >
            {detail.render_document.title}
          </p>
        </div>
        <div
          className='mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500'
          data-testid='public-wxpost-metadata'
        >
          <CalendarDays className='h-4 w-4' />
          <span>{formatWxPostDisplayDate(detail.created_at)}</span>
          <span aria-hidden='true'>·</span>
          <span>Revision {detail.article_revision}</span>
        </div>
        {canDelete && (
          <div className='absolute right-0 top-0 flex items-center gap-2'>
            <button
              type='button'
              className='inline-flex h-9 w-9 items-center justify-center rounded-full border border-blue-200 bg-white text-blue-700 shadow-sm transition hover:border-blue-300 hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-200 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-300 disabled:shadow-none'
              disabled={wechatPreviewPending}
              onClick={() => void openWechatPreview()}
              aria-label='Open WeChat draft preview'
              title='Open WeChat draft preview'
              data-testid='preview-wechat-draft'
            >
              {wechatPreviewPending ? (
                <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
              ) : (
                <Eye className='h-4 w-4' aria-hidden='true' />
              )}
            </button>
            <button
              type='button'
              className='inline-flex h-9 w-9 items-center justify-center rounded-full border border-emerald-200 bg-white text-emerald-700 shadow-sm transition hover:border-emerald-300 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200'
              onClick={openWechatDialog}
              aria-label='Publish to WeChat Drafts'
              title='Publish to WeChat Drafts'
              data-testid='publish-wechat-draft'
            >
              <WechatIcon />
            </button>
            <button
              type='button'
              className='inline-flex h-9 w-9 items-center justify-center rounded-full border border-red-200 bg-white text-red-700 shadow-sm transition hover:border-red-300 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-200'
              onClick={() => {
                setDeleteError(null);
                setDeleteConfirming(true);
              }}
              aria-label='Delete public revision'
              title='Delete public revision'
              data-testid='delete-public-wxpost'
            >
              <Trash2 className='h-4 w-4' aria-hidden='true' />
            </button>
          </div>
        )}
      </div>

      <WxPostPresentationDrawer
        value={selection}
        onChange={setSelection}
        onReset={() => setSelection(defaultSelection)}
        renderMode={renderMode}
        onRenderModeChange={setRenderMode}
        charCounts={charCounts}
      />

      <div className='hidden sm:block'>
        <WxPostPresentationControls
          value={selection}
          onChange={setSelection}
          onReset={() => setSelection(defaultSelection)}
          renderMode={renderMode}
          onRenderModeChange={setRenderMode}
          charCounts={charCounts}
        />
      </div>

      <WxPostRenderer
        article={detail.render_document}
        previewSize={selection.previewSize}
        html={renderMode === 'mini' ? miniHtml : canonicalHtml}
      />

      <footer className='mx-auto mt-10 max-w-3xl border-t border-slate-200 py-6 text-center text-xs text-slate-500'>
        Published by SoarHigh Toastmasters · Presentation choices will be used
        when publishing to WeChat Drafts.
      </footer>

      {deleteConfirming && (
        <ConfirmActionDialog
          title='Delete public WxPost?'
          error={deleteError}
          pending={deletePending}
          confirmLabel='Delete public WxPost'
          pendingLabel='Deleting…'
          dismissOnBackdrop
          testId='delete-public-wxpost-dialog'
          onCancel={() => setDeleteConfirming(false)}
          onConfirm={() => void confirmDelete()}
        >
          This removes the public revision and its public media. The private
          workspace, Saved Draft, and any existing WeChat draft will remain.
        </ConfirmActionDialog>
      )}

      {wechatOpen && (
        <ConfirmActionDialog
          title={
            wechatStatus?.state === 'uncertain'
              ? 'Recover WeChat Draft?'
              : 'Publish to WeChat Drafts?'
          }
          error={wechatError}
          pending={wechatPending}
          confirmLabel={
            wechatStatus?.state === 'uncertain'
              ? 'Retry Recovery'
              : 'Publish to WeChat Drafts'
          }
          pendingLabel={
            wechatStatus?.state === 'uncertain' ? 'Recovering…' : 'Publishing…'
          }
          confirmTone='success'
          dismissOnBackdrop
          testId='publish-wechat-draft-dialog'
          onCancel={() => setWechatOpen(false)}
          onConfirm={() => void confirmWechat()}
        >
          {wechatStatus?.state === 'uncertain' ? (
            <>
              <span className='block'>
                Retry searches the Official Account draft box for the exact
                Revision {detail.article_revision} content without creating a
                second draft.
              </span>
              <button
                type='button'
                className='mt-2 font-semibold text-red-700 underline decoration-red-300 underline-offset-2 hover:text-red-800'
                onClick={() => {
                  setWechatOpen(false);
                  setWechatResetError(null);
                  setWechatResetConfirming(true);
                }}
              >
                I checked; no matching draft exists
              </button>
            </>
          ) : (
            <span className='block'>
              Revision {detail.article_revision} · {publishPresentation.layout}{' '}
              · {publishPresentation.palette} · {publishPresentation.appearance}{' '}
              · {publishPresentation.typeface}. This creates or updates a draft
              only; it does not publish or send the article.
            </span>
          )}
          {hasVideo && (
            <span className='mt-2 block font-medium text-red-700'>
              Video blocks are not supported for WeChat Drafts in Phase 3.
            </span>
          )}
        </ConfirmActionDialog>
      )}

      {wechatResetConfirming && (
        <ConfirmActionDialog
          title='Reset uncertain WeChat operation?'
          error={wechatResetError}
          pending={wechatResetPending}
          confirmLabel='Reset WeChat State'
          pendingLabel='Resetting…'
          dismissOnBackdrop
          testId='reset-uncertain-wechat-draft-dialog'
          onCancel={() => setWechatResetConfirming(false)}
          onConfirm={() => void confirmWechatReset()}
        >
          Continue only after checking the Official Account draft box and
          confirming that no matching draft exists. Resetting the state when a
          draft does exist can cause a duplicate on the next publish.
        </ConfirmActionDialog>
      )}
    </>
  );
}

export default function WxPostPage() {
  const params = useParams();
  const slug = typeof params?.slug === 'string' ? params.slug : '';
  const { data: user } = useAuth();
  const { data, isPending, error } = useWxPost(slug);

  return (
    <div className='min-h-screen bg-slate-100 px-4 py-8 sm:px-6 sm:py-10'>
      <div className='mx-auto max-w-6xl'>
        <Link
          href='/posts'
          className='mb-7 inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-950'
        >
          <ArrowLeft className='h-4 w-4' />
          Back to Posts
        </Link>

        {isPending && (
          <div className='grid min-h-[55vh] place-items-center'>
            <div className='text-center text-slate-500'>
              <Loader2 className='mx-auto h-8 w-8 animate-spin text-blue-600' />
              <p className='mt-3 text-sm'>Loading WxPost…</p>
            </div>
          </div>
        )}

        {error && (
          <div className='rounded-2xl border border-red-200 bg-red-50 p-6 text-red-800'>
            <h1 className='font-semibold'>This WxPost is not available.</h1>
            <p className='mt-1 text-sm'>
              It may have been removed or is not public yet.
            </p>
          </div>
        )}

        {data && (
          <PublicWxPost key={data.id} detail={data} canDelete={Boolean(user)} />
        )}
      </div>
    </div>
  );
}
