'use client';

import { ArrowLeft, CalendarDays, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';

import {
  WxPostPresentationControls,
  type WxPostPresentationSelection,
} from '@/components/wxpost/WxPostPresentationControls';
import { WxPostPresentationDrawer } from '@/components/wxpost/WxPostPresentationDrawer';
import { WxPostRenderer } from '@/components/wxpost/WxPostRenderer';
import { formatWxPostDisplayDate } from '@/components/wxpost/renderer/context';
import type { WxPostPublicDetail } from '@/components/wxpost/types';
import { useWxPost } from '@/hooks/useWxPost';

function PublicWxPost({ detail }: { detail: WxPostPublicDetail }) {
  const defaultSelection: WxPostPresentationSelection = {
    ...detail.render_document.presentation,
    previewSize: 'mobile-390',
  };
  const [selection, setSelection] =
    useState<WxPostPresentationSelection>(defaultSelection);

  return (
    <>
      <div className='mb-7 flex flex-wrap items-end justify-between gap-4'>
        <div>
          <div className='mb-3 flex flex-wrap items-center gap-2'>
            <span className='rounded-full bg-gradient-to-r from-blue-600 to-purple-600 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-white'>
              WxPost
            </span>
            <span className='text-xs font-medium uppercase tracking-[0.12em] text-slate-500'>
              {detail.context_label}
            </span>
          </div>
          <p className='max-w-3xl text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl'>
            {detail.render_document.title}
          </p>
        </div>
        <div className='flex items-center gap-2 text-xs text-slate-500'>
          <CalendarDays className='h-4 w-4' />
          <span>{formatWxPostDisplayDate(detail.created_at)}</span>
          <span aria-hidden='true'>·</span>
          <span>Revision {detail.article_revision}</span>
        </div>
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
          contextLabel: detail.context_label,
          displayDate: formatWxPostDisplayDate(detail.created_at),
          publisherName: 'SoarHigh Toastmasters',
        }}
      />

      <footer className='mx-auto mt-10 max-w-3xl border-t border-slate-200 py-6 text-center text-xs text-slate-500'>
        Published by SoarHigh Toastmasters · Presentation choices affect only
        this preview.
      </footer>
    </>
  );
}

export default function WxPostPage() {
  const params = useParams();
  const slug = typeof params?.slug === 'string' ? params.slug : '';
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

        {data && <PublicWxPost key={data.id} detail={data} />}
      </div>
    </div>
  );
}
