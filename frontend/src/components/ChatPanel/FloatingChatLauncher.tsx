'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bot, MessageCircle, X } from 'lucide-react';
import { UnifiedChatPanel } from './UnifiedChatPanel';
import { AgendaSnapshot } from './types';

function generateAgentSessionKey(meetingId?: string): string {
  const uuidLike =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return meetingId
    ? `agent:edit:${meetingId}:${uuidLike}`
    : `agent:new:${uuidLike}`;
}

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
  const [agentSessionKey, setAgentSessionKey] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Wait for client-side mount before portal-ing into document.body (SSR-safe).
  useEffect(() => setMounted(true), []);

  const onOpen = () => {
    if (!agentSessionKey) {
      setAgentSessionKey(generateAgentSessionKey(meetingId));
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
          aria-label='Open assistant'
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
      {/* Keep the panel mounted once it's been opened once, so conversation state
          (messages, in-flight SSE consumers, etc.) survives close/reopen toggles.
          Hide it with CSS when `open` is false. */}
      {agentSessionKey && (
        <div
          role='dialog'
          aria-label='Assistant'
          className={`fixed z-50 bg-white border border-gray-200 rounded-xl shadow-2xl
                     flex-col overflow-hidden overscroll-contain
                     right-4 bottom-4 w-96 h-[640px] max-h-[calc(100vh-7rem)]
                     max-md:inset-x-2 max-md:w-auto max-md:h-[65vh]
                     ${open ? 'flex' : 'hidden'}`}
        >
          <div className='flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50'>
            <div className='flex items-center gap-2'>
              <div className='flex items-center justify-center h-6 w-6 rounded-full bg-indigo-100'>
                <Bot className='w-3.5 h-3.5 text-indigo-600' />
              </div>
              <span className='text-sm font-semibold text-gray-900'>
                Assistant
              </span>
            </div>
            <button
              type='button'
              onClick={() => setOpen(false)}
              aria-label='Close assistant'
              className='text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-md p-1 transition-colors'
            >
              <X className='w-4 h-4' />
            </button>
          </div>
          <div className='flex-1 min-h-0'>
            <UnifiedChatPanel
              sessionKey={agentSessionKey}
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
