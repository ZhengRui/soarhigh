'use client';

import { Loader2 } from 'lucide-react';
import { useId, type ReactNode } from 'react';

import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';

export function WorkspaceConflictDialog({
  title,
  children,
  error,
  pending,
  testId,
  onKeepCurrent,
  onLoadLatest,
}: {
  title: string;
  children: ReactNode;
  error: string | null;
  pending: boolean;
  testId: string;
  onKeepCurrent: () => void;
  onLoadLatest: () => void;
}) {
  const titleId = useId();

  return (
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
            className={SECONDARY_BUTTON_CLASS}
            disabled={pending}
            onClick={onKeepCurrent}
          >
            Keep current edits
          </button>
          <button
            type='button'
            className={PRIMARY_BUTTON_CLASS}
            disabled={pending}
            onClick={onLoadLatest}
          >
            {pending && <Loader2 className='animate-spin' aria-hidden='true' />}
            {pending ? 'Loading…' : 'Load latest'}
          </button>
        </div>
      </div>
    </div>
  );
}
