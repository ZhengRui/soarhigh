'use client';

import { useState } from 'react';
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

  return (
    <>
      {!open && (
        <button
          onClick={onOpen}
          aria-label='Open meeting assistant'
          className='fixed bottom-6 right-6 z-40 rounded-full shadow-lg bg-blue-500 text-white p-3 hover:bg-blue-600 transition'
        >
          <MessageCircle className='w-6 h-6' />
        </button>
      )}
      {open && sessionKey && (
        <div
          className='fixed z-40 bg-white shadow-2xl rounded-lg border flex flex-col
                     right-4 bottom-4 top-4 w-96
                     max-md:inset-x-2 max-md:top-auto max-md:bottom-2 max-md:h-[60vh] max-md:w-auto'
          role='dialog'
          aria-label='Meeting assistant'
        >
          <div className='flex items-center justify-between px-3 py-2 border-b'>
            <span className='text-sm font-medium'>Meeting Assistant</span>
            <button
              onClick={() => setOpen(false)}
              aria-label='Close meeting assistant'
              className='text-gray-500 hover:text-gray-800'
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
}
