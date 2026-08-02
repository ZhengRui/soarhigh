'use client';

import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CalendarDays, Loader2, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState } from 'react';
import toast from 'react-hot-toast';

import { ConfirmActionDialog } from '@/components/ConfirmActionDialog';
import {
  WxPostPresentationControls,
  type WxPostPresentationSelection,
} from '@/components/wxpost/WxPostPresentationControls';
import { WxPostPresentationDrawer } from '@/components/wxpost/WxPostPresentationDrawer';
import { WxPostRenderer } from '@/components/wxpost/WxPostRenderer';
import { formatWxPostDisplayDate } from '@/components/wxpost/renderer/context';
import type { WxPostPublicDetail } from '@/components/wxpost/types';
import { useAuth } from '@/hooks/useAuth';
import { useWxPost } from '@/hooks/useWxPost';
import { deletePublicWxPost } from '@/utils/wxposts';

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
        <div className={canDelete ? 'min-w-0 pr-12' : 'min-w-0'}>
          <div className='mb-3 flex flex-wrap items-center gap-2'>
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
          <button
            type='button'
            className='absolute right-0 top-0 inline-flex h-9 w-9 items-center justify-center rounded-full border border-red-200 bg-white text-red-700 shadow-sm transition hover:border-red-300 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-200'
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
        )}
      </div>

      <WxPostPresentationDrawer
        value={selection}
        onChange={setSelection}
        onReset={() => setSelection(defaultSelection)}
      />

      <div className='hidden sm:block'>
        <WxPostPresentationControls
          value={selection}
          onChange={setSelection}
          onReset={() => setSelection(defaultSelection)}
        />
      </div>

      <WxPostRenderer
        article={detail.render_document}
        presentation={{
          layout: selection.layout,
          palette: selection.palette,
          appearance: selection.appearance,
          typeface: selection.typeface,
        }}
        previewSize={selection.previewSize}
        context={{
          displayDate: formatWxPostDisplayDate(detail.created_at),
          publisherName: 'SoarHigh Toastmasters',
        }}
      />

      <footer className='mx-auto mt-10 max-w-3xl border-t border-slate-200 py-6 text-center text-xs text-slate-500'>
        Published by SoarHigh Toastmasters · Presentation choices affect only
        this preview.
      </footer>

      {deleteConfirming && (
        <ConfirmActionDialog
          title='Delete public WxPost?'
          error={deleteError}
          pending={deletePending}
          confirmLabel='Delete public WxPost'
          pendingLabel='Deleting…'
          testId='delete-public-wxpost-dialog'
          onCancel={() => setDeleteConfirming(false)}
          onConfirm={() => void confirmDelete()}
        >
          This removes the public revision and its public media. The private
          workspace and Draft will remain.
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
