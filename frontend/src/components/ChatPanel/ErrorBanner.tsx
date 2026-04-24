'use client';

import { AlertTriangle, RefreshCw, X } from 'lucide-react';

export type ChatError = {
  reason: string;
  recoverable: boolean;
  message: string;
};

export function ErrorBanner({
  error,
  onRetry,
  onDismiss,
}: {
  error: ChatError;
  onRetry?: () => void;
  onDismiss: () => void;
}) {
  const palette = error.recoverable
    ? 'bg-amber-50 border-amber-300 text-amber-900'
    : 'bg-red-50 border-red-300 text-red-900';
  const icon = error.recoverable ? (
    <AlertTriangle className='w-4 h-4 shrink-0' />
  ) : (
    <X className='w-4 h-4 shrink-0' />
  );
  return (
    <div
      className={`flex items-start gap-2 mx-3 mt-2 px-3 py-2 rounded-md border text-xs ${palette}`}
    >
      <span className='pt-0.5'>{icon}</span>
      <div className='flex-1 min-w-0 leading-snug'>
        <div className='font-semibold mb-0.5'>
          {error.recoverable ? 'Request failed' : 'Something went wrong'}
        </div>
        <div className='break-words opacity-90'>{error.message}</div>
        {!error.recoverable && (
          <div className='mt-1 opacity-75'>
            Try using Manual mode, or refresh and start over.
          </div>
        )}
      </div>
      <div className='flex flex-col items-end gap-1 shrink-0'>
        {error.recoverable && onRetry && (
          <button
            type='button'
            onClick={onRetry}
            className='flex items-center gap-1 px-2 py-0.5 rounded border border-amber-400 bg-white
                       hover:bg-amber-100 text-amber-900 font-semibold transition-colors'
          >
            <RefreshCw className='w-3 h-3' />
            Retry
          </button>
        )}
        <button
          type='button'
          onClick={onDismiss}
          aria-label='Dismiss'
          className='text-current opacity-50 hover:opacity-100 transition-opacity'
        >
          <X className='w-3.5 h-3.5' />
        </button>
      </div>
    </div>
  );
}
