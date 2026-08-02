'use client';

import { Check, ImageIcon, Loader2, X } from 'lucide-react';
import { useId } from 'react';
import { createPortal } from 'react-dom';

import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';

export interface WxPostCoverCandidate {
  id: string;
  filename: string;
  previewUrl: string | null;
  inArticle: boolean;
}

export function WxPostCoverPicker({
  candidates,
  currentCoverId,
  selectedCoverId,
  loading,
  onSelect,
  onClose,
  onApply,
}: {
  candidates: WxPostCoverCandidate[];
  currentCoverId: string | null;
  selectedCoverId: string | null;
  loading: boolean;
  onSelect: (id: string | null) => void;
  onClose: () => void;
  onApply: () => void;
}) {
  const titleId = useId();
  const selectionChanged = selectedCoverId !== currentCoverId;

  return createPortal(
    <div
      className='fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4 max-[640px]:items-end max-[640px]:p-0'
      role='dialog'
      aria-modal='true'
      aria-labelledby={titleId}
      data-testid='cover-picker-dialog'
    >
      <div className='flex max-h-[min(760px,calc(100dvh-2rem))] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl max-[640px]:max-h-[88dvh] max-[640px]:rounded-b-none max-[640px]:rounded-t-2xl'>
        <div className='flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4'>
          <div>
            <h2 id={titleId} className='m-0 text-lg font-bold text-slate-900'>
              Choose cover image
            </h2>
            <p className='mb-0 mt-1 text-sm text-slate-500'>
              The cover does not have to appear inside the article.
            </p>
          </div>
          <button
            type='button'
            className='grid h-9 w-9 shrink-0 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900'
            aria-label='Close cover picker'
            onClick={onClose}
          >
            <X className='h-5 w-5' />
          </button>
        </div>

        <div className='min-h-0 flex-1 overflow-y-auto p-4 sm:p-5'>
          {candidates.length > 0 ? (
            <div className='grid grid-cols-2 gap-3 sm:grid-cols-3'>
              {candidates.map((candidate) => {
                const selected = candidate.id === selectedCoverId;
                const current = candidate.id === currentCoverId;
                return (
                  <button
                    key={candidate.id}
                    type='button'
                    className={`group min-w-0 overflow-hidden rounded-xl border-2 bg-white text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                      selected
                        ? 'border-blue-600 shadow-sm'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                    aria-pressed={selected}
                    onClick={() => onSelect(candidate.id)}
                    data-testid={`cover-candidate-${candidate.id}`}
                  >
                    <div className='relative aspect-[4/3] overflow-hidden bg-slate-100'>
                      {candidate.previewUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={candidate.previewUrl}
                          alt=''
                          className='h-full w-full object-cover'
                        />
                      ) : (
                        <div className='grid h-full place-items-center text-slate-400'>
                          {loading ? (
                            <Loader2 className='h-5 w-5 animate-spin' />
                          ) : (
                            <ImageIcon className='h-6 w-6' />
                          )}
                        </div>
                      )}
                      {selected && (
                        <span className='absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full bg-blue-600 text-white shadow'>
                          <Check className='h-4 w-4' />
                        </span>
                      )}
                    </div>
                    <div className='grid min-w-0 gap-1 p-3'>
                      <div className='flex items-center gap-2'>
                        <strong className='text-sm text-slate-900'>
                          {candidate.id}
                        </strong>
                        {current && (
                          <span className='rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-700'>
                            Current cover
                          </span>
                        )}
                      </div>
                      <span className='truncate text-xs text-slate-500'>
                        {candidate.filename}
                      </span>
                      <span className='text-[11px] font-semibold text-slate-500'>
                        {candidate.inArticle ? 'In article' : 'Cover only'}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className='grid min-h-48 place-content-center justify-items-center gap-2 text-center'>
              <ImageIcon className='h-7 w-7 text-slate-400' />
              <p className='m-0 text-sm font-semibold text-slate-700'>
                No workspace images are ready
              </p>
              <p className='m-0 text-xs text-slate-500'>
                Add or import an image from Materials first.
              </p>
            </div>
          )}
        </div>

        <div className='flex items-center justify-between gap-3 border-t border-slate-200 px-5 py-4 max-[480px]:flex-col max-[480px]:items-stretch'>
          <button
            type='button'
            className={`${SECONDARY_BUTTON_CLASS} text-red-700 hover:border-red-200 hover:bg-red-50`}
            disabled={selectedCoverId === null}
            onClick={() => onSelect(null)}
          >
            Remove cover
          </button>
          <div className='flex justify-end gap-2 max-[480px]:grid max-[480px]:grid-cols-2'>
            <button
              type='button'
              className={SECONDARY_BUTTON_CLASS}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type='button'
              className={PRIMARY_BUTTON_CLASS}
              disabled={!selectionChanged}
              onClick={onApply}
              data-testid='apply-cover-selection'
            >
              {selectedCoverId ? 'Set cover' : 'Remove cover'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
