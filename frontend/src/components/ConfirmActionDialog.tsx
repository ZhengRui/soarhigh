'use client';

import { Loader2 } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export function ConfirmActionDialog({
  title,
  children,
  error,
  pending,
  confirmLabel,
  pendingLabel,
  testId,
  onCancel,
  onConfirm,
}: {
  title: string;
  children: ReactNode;
  error: string | null;
  pending: boolean;
  confirmLabel: string;
  pendingLabel: string;
  testId: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const titleId = useId();

  return createPortal(
    <div
      className='fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4'
      role='dialog'
      aria-modal='true'
      aria-labelledby={titleId}
      data-testid={testId}
    >
      <div className='w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl'>
        <h2 id={titleId} className='m-0 text-lg font-bold text-slate-900'>
          {title}
        </h2>
        <p className='mb-0 mt-3 text-sm leading-6 text-slate-600'>{children}</p>
        {error && (
          <p className='mb-0 mt-3 text-sm text-red-700' role='alert'>
            {error}
          </p>
        )}
        <div className='mt-5 flex justify-end gap-2 max-[480px]:flex-col-reverse max-[480px]:[&_button]:w-full'>
          <button
            type='button'
            className='inline-flex min-h-11 items-center justify-center rounded-[11px] border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60'
            disabled={pending}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type='button'
            className='inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-red-700 bg-red-700 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-60'
            disabled={pending}
            onClick={onConfirm}
          >
            {pending && (
              <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
            )}
            {pending ? pendingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
