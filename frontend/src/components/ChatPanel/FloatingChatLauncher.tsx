'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { MessageCircle, X } from 'lucide-react';
import { ChatPanel } from './ChatPanel';
import { AgendaSnapshot } from './types';

export function FloatingChatLauncher({
  meetingId,
  agendaSnapshot,
  onAgendaAfter,
}: {
  meetingId?: string;
  agendaSnapshot: AgendaSnapshot;
  onAgendaAfter: (a: AgendaSnapshot) => void;
}) {
  const [open, setOpen] = useState(false);
  const [sessionKey, setSessionKey] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Wait for client-side mount before portal-ing into document.body (SSR-safe).
  useEffect(() => setMounted(true), []);

  const onOpen = () => {
    if (!sessionKey) {
      const uuidLike =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID().slice(0, 8)
          : Math.random().toString(36).slice(2, 10);
      setSessionKey(
        meetingId ? `edit:${meetingId}:${uuidLike}` : `new:${uuidLike}`
      );
    }
    setOpen(true);
  };

  if (!mounted) return null;

  const node = (
    <>
      {!open && (
        <button
          type='button'
          onClick={onOpen}
          aria-label='Open meeting assistant'
          className='fixed bottom-6 right-6 z-50 flex items-center justify-center
                     h-12 w-12 rounded-full
                     bg-indigo-600 hover:bg-indigo-700
                     text-white
                     shadow-lg hover:shadow-xl
                     focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500
                     transition-all'
        >
          <MessageCircle className='w-5 h-5' />
        </button>
      )}
      {open && sessionKey && (
        <div
          role='dialog'
          aria-label='Meeting assistant'
          className='fixed z-50 bg-white border border-gray-200 rounded-xl shadow-2xl
                     flex flex-col overflow-hidden
                     right-4 bottom-4 top-4 w-96
                     max-md:inset-x-2 max-md:top-auto max-md:bottom-2 max-md:h-[60vh] max-md:w-auto'
        >
          <div className='flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50'>
            <div className='flex items-center gap-2'>
              <div className='flex items-center justify-center h-6 w-6 rounded-full bg-indigo-100'>
                <MessageCircle className='w-3.5 h-3.5 text-indigo-600' />
              </div>
              <span className='text-sm font-semibold text-gray-900'>
                Meeting Assistant
              </span>
            </div>
            <button
              type='button'
              onClick={() => setOpen(false)}
              aria-label='Close meeting assistant'
              className='text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-md p-1 transition-colors'
            >
              <X className='w-4 h-4' />
            </button>
          </div>
          <div className='flex-1 min-h-0'>
            <ChatPanel
              sessionKey={sessionKey}
              agendaSnapshot={agendaSnapshot}
              onAgendaAfter={onAgendaAfter}
            />
          </div>
        </div>
      )}
    </>
  );

  return createPortal(node, document.body);
}
