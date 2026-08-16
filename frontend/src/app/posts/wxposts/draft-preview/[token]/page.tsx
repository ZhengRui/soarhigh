import { headers } from 'next/headers';
import { notFound } from 'next/navigation';

import { compileWxPost } from '@/components/wxpost/renderer/compiler';
import type { WxPostRenderDocument } from '@/components/wxpost/types';

import { MediaRetryActivator } from './MediaRetry';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'Temporary WxPost Draft Preview',
  robots: { index: false, follow: false },
};

interface DraftPreviewPayload {
  workspaceId: string;
  draftVersion: number;
  renderDocument: WxPostRenderDocument;
  assetDimensions?: Record<string, { width: number; height: number }>;
}

function apiUrl(path: string) {
  const base = (process.env.NEXT_PUBLIC_API_ENDPOINT ?? '').replace(/\/$/, '');
  return `${base}${path}`;
}

function isDraftPreviewPayload(value: unknown): value is DraftPreviewPayload {
  if (!value || typeof value !== 'object') return false;
  const payload = value as Partial<DraftPreviewPayload>;
  return Boolean(
    typeof payload.workspaceId === 'string' &&
      Number.isInteger(payload.draftVersion) &&
      payload.renderDocument &&
      typeof payload.renderDocument === 'object'
  );
}

export default async function WxPostDraftPreviewPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const requestHeaders = await headers();
  const protocol = requestHeaders.get('x-forwarded-proto') ?? 'http';
  const host =
    requestHeaders.get('x-forwarded-host') ?? requestHeaders.get('host');
  if (!host) notFound();
  const previewOrigin = `${protocol}://${host}`;
  const endpoint = apiUrl(
    `/posts/wxposts/draft-previews/${encodeURIComponent(token)}`
  );
  const response = await fetch(endpoint, { cache: 'no-store' });
  if (!response.ok) notFound();

  const payload: unknown = await response.json();
  if (!isDraftPreviewPayload(payload)) notFound();

  const renderDocument: WxPostRenderDocument = {
    ...payload.renderDocument,
    media: payload.renderDocument.media.map((media) => ({
      ...media,
      sourceUrl: `${previewOrigin}/api/wxpost/draft-preview/${encodeURIComponent(token)}/media/${encodeURIComponent(media.id)}`,
      posterUrl: null,
    })),
  };
  const assetUrls = Object.fromEntries(
    renderDocument.media.map((media) => [media.id, media.sourceUrl])
  );
  const assetDimensions = Object.fromEntries(
    Object.entries(payload.assetDimensions ?? {}).filter(
      ([, dimensions]) =>
        Number.isInteger(dimensions?.width) &&
        Number.isInteger(dimensions?.height) &&
        dimensions.width > 0 &&
        dimensions.height > 0
    )
  );
  const { html } = compileWxPost({
    renderDocument,
    presentation: renderDocument.presentation,
    context: {
      assetUrls,
      assetDimensions,
      publisherName: 'SoarHigh Toastmasters',
    },
  });

  return (
    <main className='min-h-screen bg-slate-100 px-3 py-5 sm:px-6 sm:py-8'>
      <div className='mx-auto mb-4 flex max-w-4xl items-center justify-between gap-3 text-xs text-slate-500'>
        <span>Temporary Draft preview</span>
        <span>Draft v{payload.draftVersion}</span>
      </div>
      <div
        className='mx-auto max-w-4xl'
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <MediaRetryActivator />
    </main>
  );
}
