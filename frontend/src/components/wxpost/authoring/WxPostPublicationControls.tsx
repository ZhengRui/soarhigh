'use client';

import { ExternalLink, Globe2, Loader2, UploadCloud } from 'lucide-react';
import { useId, useState } from 'react';
import { createPortal } from 'react-dom';

import type { WorkspacePublicationStatus } from '@/utils/wxpostWorkspace';

import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';

export function WxPostPublicationControls({
  status,
  loading,
  loadError,
  dirty,
  pending,
  uploading,
  currentDraftVersion,
  onSync,
}: {
  status: WorkspacePublicationStatus | null;
  loading: boolean;
  loadError: boolean;
  dirty: boolean;
  pending: boolean;
  uploading: { done: number; total: number } | null;
  currentDraftVersion: number;
  onSync: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const titleId = useId();
  const published =
    status?.state === 'up-to-date' || status?.state === 'update-available';
  const update = Boolean(
    published &&
      (status?.state === 'update-available' ||
        status?.sourceDraftVersion !== currentDraftVersion)
  );
  const syncAvailable = Boolean(
    status &&
      status.state !== 'unavailable' &&
      (status.state === 'not-synced' || update)
  );
  const statusText = published
    ? `Public revision ${status.publicRevision} · from Draft v${status.sourceDraftVersion} · ${
        update ? `Draft v${currentDraftVersion} ready to publish` : 'up to date'
      }`
    : status?.state === 'unavailable'
      ? 'Public status unavailable'
      : `Not published · Draft v${currentDraftVersion}`;

  return (
    <>
      <div
        className='flex min-h-9 flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3'
        data-testid='draft-publication-controls'
      >
        <div className='flex min-w-0 items-center gap-2 text-xs text-slate-600'>
          <Globe2
            className='h-4 w-4 shrink-0 text-blue-600'
            aria-hidden='true'
          />
          {loading && !status ? (
            <span>Checking public status…</span>
          ) : loadError ? (
            <span data-testid='publication-status'>
              Public status unavailable
            </span>
          ) : (
            <span data-testid='publication-status'>{statusText}</span>
          )}
          {loading && status && (
            <Loader2
              className='h-3.5 w-3.5 animate-spin text-blue-500'
              aria-label='Refreshing public status'
              data-testid='publication-refresh-spinner'
            />
          )}
        </div>
        <div
          className='ml-auto flex shrink-0 items-center gap-2 max-[480px]:ml-0 max-[480px]:basis-full max-[480px]:gap-1'
          data-testid='publication-actions'
        >
          {!loadError && status && (
            <>
              {published && status.publicUrl && (
                <a
                  href={status.publicUrl}
                  target='_blank'
                  rel='noreferrer'
                  className={`${SECONDARY_BUTTON_CLASS} min-h-9 px-3 text-xs no-underline max-[900px]:h-9 max-[900px]:w-9 max-[900px]:p-0`}
                  data-testid='view-public-wxpost'
                >
                  <ExternalLink aria-hidden='true' />
                  <span className='max-[900px]:sr-only'>
                    View Public WxPost
                  </span>
                </a>
              )}
            </>
          )}
          <button
            type='button'
            className={`${PRIMARY_BUTTON_CLASS} min-h-9 px-3 text-xs max-[900px]:h-9 max-[900px]:w-9 max-[900px]:p-0`}
            disabled={!syncAvailable || dirty || pending || loading}
            title={
              dirty
                ? 'Save Draft before updating the public WxPost.'
                : !syncAvailable && published
                  ? 'The public WxPost is up to date.'
                  : undefined
            }
            onClick={() => setConfirming(true)}
            data-testid='sync-public-wxpost'
          >
            {pending || (loading && !status) ? (
              <Loader2 className='animate-spin' aria-hidden='true' />
            ) : (
              <UploadCloud aria-hidden='true' />
            )}
            <span className='max-[900px]:sr-only'>Update Public WxPost</span>
          </button>
        </div>
      </div>

      {confirming &&
        status &&
        createPortal(
          <div
            className='fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4'
            role='dialog'
            aria-modal='true'
            aria-labelledby={titleId}
            data-testid='publication-confirm-dialog'
          >
            <div className='w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl'>
              <h2 id={titleId} className='m-0 text-lg font-bold text-slate-900'>
                {update ? 'Update public WxPost?' : 'Publish this saved Draft?'}
              </h2>
              <p className='mb-0 mt-3 text-sm leading-6 text-slate-600'>
                {update
                  ? `Draft v${status.currentDraftVersion} will replace the current public revision after every asset is ready.`
                  : 'Anyone with the link will be able to view this saved Draft after every asset is ready.'}
              </p>
              <div className='mt-5 flex justify-end gap-2 max-[480px]:flex-col-reverse max-[480px]:[&_button]:w-full'>
                <button
                  type='button'
                  className={SECONDARY_BUTTON_CLASS}
                  disabled={pending}
                  onClick={() => setConfirming(false)}
                >
                  Cancel
                </button>
                <button
                  type='button'
                  className={PRIMARY_BUTTON_CLASS}
                  disabled={pending}
                  onClick={() => {
                    void onSync().then(() => setConfirming(false));
                  }}
                >
                  {pending && (
                    <Loader2 className='animate-spin' aria-hidden='true' />
                  )}
                  {pending
                    ? uploading
                      ? `Uploading images (${uploading.done + 1}/${uploading.total})…`
                      : 'Synchronizing…'
                    : update
                      ? 'Update Public WxPost'
                      : 'Publish WxPost'}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
