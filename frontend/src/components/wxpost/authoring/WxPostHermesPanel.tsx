'use client';

import { ArrowUp, Loader2, Sparkles, X } from 'lucide-react';

import type { WorkspaceDraftSession } from '@/utils/wxpostWorkspace';

export function WxPostHermesPanel({
  mobile,
  session,
  sessionStatus,
  chatPending,
  selectedText,
  message,
  dirty,
  onClose,
  onClearSelection,
  onMessageChange,
  onSend,
}: {
  mobile: boolean;
  session: WorkspaceDraftSession | null;
  sessionStatus: 'connecting' | 'online' | 'unavailable';
  chatPending: boolean;
  selectedText: string | null;
  message: string;
  dirty: boolean;
  onClose: () => void;
  onClearSelection: () => void;
  onMessageChange: (message: string) => void;
  onSend: () => void;
}) {
  return (
    <div className='flex h-full min-h-0 flex-col bg-white'>
      <div className='flex items-start justify-between border-b border-slate-200 px-4 py-3'>
        <div>
          <div className='flex items-center gap-2'>
            <Sparkles className='h-4 w-4 text-blue-600' aria-hidden='true' />
            <h2 className='m-0 text-sm font-bold text-slate-900'>
              Hermes editor
            </h2>
          </div>
          <p className='mb-0 mt-1 text-[11px] text-slate-500'>
            Revisions are saved as a new Draft version.
          </p>
        </div>
        <div className='flex items-center gap-2'>
          <span
            className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
              sessionStatus === 'online'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            {sessionStatus === 'connecting'
              ? 'Connecting…'
              : sessionStatus === 'online'
                ? 'Online'
                : 'Unavailable'}
          </span>
          {mobile && (
            <button
              type='button'
              className='grid h-8 w-8 place-items-center rounded-full border border-slate-200 text-slate-500'
              aria-label='Close Hermes editor'
              onClick={onClose}
            >
              <X className='h-4 w-4' />
            </button>
          )}
        </div>
      </div>
      <div
        className='grid min-h-52 flex-1 content-start gap-3 overflow-y-auto bg-slate-50/60 p-4'
        aria-live='polite'
        data-testid={
          mobile ? 'mobile-draft-chat-history' : 'draft-chat-history'
        }
      >
        {(session?.messages ?? []).length === 0 ? (
          <div className='grid min-h-44 place-content-center text-center text-sm text-slate-500'>
            <Sparkles className='mx-auto mb-2 h-5 w-5 text-blue-500' />
            Ask Hermes to revise the saved Draft.
          </div>
        ) : (
          session?.messages.map((item, index) => (
            <p
              key={`${item.role}-${index}`}
              className={`m-0 max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm leading-6 ${
                item.role === 'user'
                  ? 'ml-auto rounded-br-md bg-blue-600 text-white'
                  : 'rounded-bl-md border border-slate-200 bg-white text-slate-700'
              }`}
            >
              {item.text}
            </p>
          ))
        )}
        {chatPending && (
          <p className='m-0 flex items-center gap-2 text-sm text-slate-500'>
            <Loader2 className='h-4 w-4 animate-spin' />
            Hermes is revising…
          </p>
        )}
      </div>
      <div className='border-t border-slate-200 p-3'>
        {selectedText && (
          <div className='mb-2 flex items-start gap-2 rounded-lg bg-blue-50 p-2 text-xs text-blue-900'>
            <span className='line-clamp-2 flex-1'>“{selectedText}”</span>
            <button
              type='button'
              className='rounded p-0.5 hover:bg-blue-100'
              aria-label='Clear selected text'
              onClick={onClearSelection}
            >
              <X className='h-3.5 w-3.5' />
            </button>
          </div>
        )}
        <div className='rounded-xl border border-slate-300 bg-white p-2 focus-within:border-blue-500'>
          <textarea
            className='block min-h-20 w-full resize-y border-0 bg-transparent p-1 text-sm outline-none'
            placeholder='Ask Hermes to revise the draft…'
            value={message}
            disabled={chatPending}
            onChange={(event) => onMessageChange(event.target.value)}
          />
          <div className='mt-1 flex items-center justify-between gap-2'>
            <span className='text-[10px] font-medium text-slate-500'>
              {selectedText
                ? 'Selection attached'
                : dirty
                  ? 'Save local edits first'
                  : 'Works on the saved Draft'}
            </span>
            <button
              type='button'
              className='grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:bg-slate-300'
              aria-label='Send revision request'
              disabled={!message.trim() || dirty || chatPending}
              title={
                dirty ? 'Save local edits before asking Hermes.' : undefined
              }
              onClick={onSend}
              data-testid={
                mobile ? 'send-mobile-draft-chat' : 'send-draft-chat'
              }
            >
              <ArrowUp className='h-4 w-4' />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
