'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BarChart3, Bot, MessageCircle, Pencil, X } from 'lucide-react';
import { ChatPanel } from './ChatPanel';
import { StatsChatPanel } from './StatsChatPanel';
import { UnifiedChatPanel } from './UnifiedChatPanel';
import { AgendaSnapshot } from './types';

type Mode = 'agent' | 'meeting' | 'stats';

function generateAgentSessionKey(meetingId?: string): string {
  const uuidLike =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return meetingId
    ? `agent:edit:${meetingId}:${uuidLike}`
    : `agent:new:${uuidLike}`;
}

function generateStatsSessionKey(): string {
  // Stats session id is regenerated per page load (NOT persisted to
  // localStorage). Same lifecycle as the meeting session id — fresh on
  // each browser load, preserved by useState across mode toggles within
  // the same load. Persisting in localStorage would silently re-attach
  // every visit to the same backend session, dragging the model's prior
  // turns (cached tool results, prior numeric answers) into the next
  // agent run via `history_cursor` — observed bug where the model
  // recaps "我们之前讨论了 Jessica…" from a session days earlier.
  const uuidLike =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `stats:${uuidLike}`;
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
  const [mode, setMode] = useState<Mode>('agent');
  const [agentSessionKey, setAgentSessionKey] = useState<string | null>(null);
  const [sessionKey, setSessionKey] = useState<string | null>(null);
  const [statsSessionKey, setStatsSessionKey] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Wait for client-side mount before portal-ing into document.body (SSR-safe).
  useEffect(() => setMounted(true), []);

  const onOpen = () => {
    if (!agentSessionKey) {
      setAgentSessionKey(generateAgentSessionKey(meetingId));
    }
    if (!sessionKey) {
      const uuidLike =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID().slice(0, 8)
          : Math.random().toString(36).slice(2, 10);
      setSessionKey(
        meetingId ? `edit:${meetingId}:${uuidLike}` : `new:${uuidLike}`
      );
    }
    if (!statsSessionKey) {
      setStatsSessionKey(generateStatsSessionKey());
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
      {/* Keep the panel mounted once it's been opened once, so conversation state
          (messages, in-flight SSE consumers, etc.) survives close/reopen toggles.
          Hide it with CSS when `open` is false. We don't set aria-hidden — the
          `hidden` Tailwind class applies display:none which already removes the
          subtree from the accessibility tree, and setting aria-hidden while the
          close button retains focus triggers a React a11y warning. */}
      {sessionKey && (
        <div
          role='dialog'
          aria-label='Meeting assistant'
          className={`fixed z-50 bg-white border border-gray-200 rounded-xl shadow-2xl
                     flex-col overflow-hidden
                     right-4 bottom-4 w-96 h-[640px] max-h-[calc(100vh-7rem)]
                     max-md:inset-x-2 max-md:w-auto max-md:h-[65vh]
                     ${open ? 'flex' : 'hidden'}`}
        >
          <div className='flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50'>
            <div className='flex items-center gap-2'>
              <div className='flex items-center justify-center h-6 w-6 rounded-full bg-indigo-100'>
                {mode === 'agent' ? (
                  <Bot className='w-3.5 h-3.5 text-indigo-600' />
                ) : mode === 'meeting' ? (
                  <MessageCircle className='w-3.5 h-3.5 text-indigo-600' />
                ) : (
                  <BarChart3 className='w-3.5 h-3.5 text-indigo-600' />
                )}
              </div>
              <span className='text-sm font-semibold text-gray-900'>
                {mode === 'agent'
                  ? 'Assistant'
                  : mode === 'meeting'
                    ? 'Meeting Assistant'
                    : 'Statistics'}
              </span>
            </div>
            <div className='flex items-center gap-1'>
              {/* Auto is the normal route. Edit / Stats stay as explicit
                  fallback paths while router quality settles. */}
              <div className='flex items-center rounded-md bg-gray-200 p-0.5 mr-1'>
                <button
                  type='button'
                  onClick={() => setMode('agent')}
                  aria-label='Automatic routing mode'
                  title='Auto route'
                  className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
                    mode === 'agent'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  <Bot className='w-3 h-3' />
                  <span>Auto</span>
                </button>
                <button
                  type='button'
                  onClick={() => setMode('meeting')}
                  aria-label='Edit meeting mode'
                  title='Edit meeting'
                  className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
                    mode === 'meeting'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  <Pencil className='w-3 h-3' />
                  <span>Edit</span>
                </button>
                <button
                  type='button'
                  onClick={() => setMode('stats')}
                  aria-label='Statistics mode'
                  title='Statistics'
                  className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
                    mode === 'stats'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  <BarChart3 className='w-3 h-3' />
                  <span>Stats</span>
                </button>
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
          </div>
          {/* Both panels stay mounted once opened so each mode's
              in-memory message list (streaming SSE state, scroll
              position, draft input) survives toggling between Edit
              and Stats. The inactive panel is hidden via display:none,
              not unmounted. */}
          {agentSessionKey && (
            <div
              className={`flex-1 min-h-0 ${mode === 'agent' ? '' : 'hidden'}`}
            >
              <UnifiedChatPanel
                sessionKey={agentSessionKey}
                agendaSnapshot={agendaSnapshot}
                onAgendaAfter={onAgendaAfter}
              />
            </div>
          )}
          <div
            className={`flex-1 min-h-0 ${mode === 'meeting' ? '' : 'hidden'}`}
          >
            <ChatPanel
              sessionKey={sessionKey}
              agendaSnapshot={agendaSnapshot}
              onAgendaAfter={onAgendaAfter}
            />
          </div>
          {statsSessionKey && (
            <div
              className={`flex-1 min-h-0 ${mode === 'stats' ? '' : 'hidden'}`}
            >
              <StatsChatPanel sessionKey={statsSessionKey} />
            </div>
          )}
        </div>
      )}
    </>
  );

  return createPortal(node, document.body);
}
