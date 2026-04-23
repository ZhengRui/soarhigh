'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import { useAgentTurn } from './useAgentTurn';
import { AgendaSnapshot, AgentTurnEvent, ChatMessage } from './types';

function uuid() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

export function ChatPanel({
  sessionKey,
  agendaSnapshot,
  onAgendaAfter,
}: {
  sessionKey: string;
  agendaSnapshot: AgendaSnapshot;
  onAgendaAfter: (a: AgendaSnapshot) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom on any message change
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    // Auto-grow the textarea to fit its content, capped at ~6 lines.
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const onEvent = useCallback(
    (ev: AgentTurnEvent) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== 'assistant') return prev;
        const next = [...prev];
        const msg = { ...last };
        if (ev.type === 'thinking')
          msg.thinking = (msg.thinking || '') + ev.data.chunk;
        if (ev.type === 'assistant_text')
          msg.content = (msg.content || '') + ev.data.chunk;
        if (ev.type === 'tool_call_start') {
          msg.toolCalls = [
            ...(msg.toolCalls || []),
            {
              id: ev.data.id,
              name: ev.data.name,
              args: ev.data.args,
              pending: true,
            },
          ];
        }
        if (ev.type === 'tool_call_end') {
          msg.toolCalls = (msg.toolCalls || []).map((tc) =>
            tc.id === ev.data.id
              ? { ...tc, pending: false, result: ev.data.result }
              : tc
          );
          onAgendaAfter(ev.data.agenda_after);
        }
        if (ev.type === 'done') {
          msg.seq = ev.data.seq;
          onAgendaAfter(ev.data.final_agenda);
        }
        if (ev.type === 'error') {
          msg.error = ev.data.message;
        }
        next[next.length - 1] = msg;
        return next;
      });
      if (ev.type === 'done' || ev.type === 'error') setLoading(false);
    },
    [onAgendaAfter]
  );

  const { send, stop } = useAgentTurn({ onEvent });

  const submit = async () => {
    if (!input.trim() || loading) return;
    const userMsg: ChatMessage = { id: uuid(), role: 'user', content: input };
    const asstMsg: ChatMessage = {
      id: uuid(),
      role: 'assistant',
      content: '',
      toolCalls: [],
    };
    setMessages((m) => [...m, userMsg, asstMsg]);
    const message = input;
    setInput('');
    setLoading(true);
    try {
      await send({
        session_id: sessionKey,
        user_message: message,
        agenda_snapshot: agendaSnapshot,
      });
    } catch {
      setLoading(false);
    }
  };

  return (
    <div className='flex flex-col h-full min-h-0 bg-white'>
      <div
        ref={scrollRef}
        className='flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-3'
      >
        {messages.length === 0 && (
          <div className='text-xs text-gray-400 text-center py-10 leading-relaxed'>
            Ask me to edit the agenda.
            <br />
            e.g. &ldquo;change SAA to Joyce&rdquo;,
            <br />
            &ldquo;move Timer 2 min later&rdquo;.
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === 'user' ? 'text-right' : 'text-left'}
          >
            <div
              className={`inline-block max-w-[85%] px-3 py-2 rounded-lg text-sm ${
                m.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {m.role === 'assistant' &&
                m.toolCalls &&
                m.toolCalls.length > 0 && (
                  <div className='flex flex-wrap gap-1 mb-1.5'>
                    {m.toolCalls.map((tc) => (
                      <span
                        key={tc.id}
                        className={`inline-flex items-center gap-1 text-[11px] font-medium px-1.5 py-0.5 rounded-md border ${
                          tc.pending
                            ? 'bg-amber-50 border-amber-200 text-amber-700'
                            : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        }`}
                      >
                        <span className='font-mono'>
                          {tc.pending ? '⋯' : '✓'}
                        </span>
                        {tc.name}
                      </span>
                    ))}
                  </div>
                )}
              <div className='whitespace-pre-wrap'>
                {m.content ||
                  (m.role === 'assistant' &&
                  !(m.toolCalls && m.toolCalls.length)
                    ? '…'
                    : '')}
              </div>
              {m.error && (
                <div className='text-red-600 text-xs mt-1'>{m.error}</div>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className='border-t border-gray-200 p-3 bg-white'>
        <div
          className='flex items-end gap-1.5 rounded-2xl border border-gray-200
                     bg-gray-50 pl-4 pr-1 py-1
                     focus-within:border-gray-300 focus-within:bg-white transition-colors'
        >
          <textarea
            ref={textareaRef}
            rows={1}
            className='flex-1 bg-transparent text-sm leading-6 text-gray-900
                       placeholder-gray-400 focus:outline-none disabled:text-gray-400
                       resize-none py-1.5 max-h-40 overflow-y-auto'
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
              // Shift+Enter falls through to default behavior (insert newline).
            }}
            placeholder='Type a message…'
            disabled={loading}
          />
          {loading ? (
            <button
              type='button'
              onClick={stop}
              aria-label='Stop'
              className='shrink-0 flex items-center justify-center h-8 w-8 rounded-full
                         bg-gray-900 text-white hover:bg-black transition-colors'
            >
              <Square className='w-3 h-3 fill-white' />
            </button>
          ) : (
            <button
              type='button'
              onClick={submit}
              aria-label='Send'
              disabled={!input.trim()}
              className='shrink-0 flex items-center justify-center h-8 w-8 rounded-full
                         bg-indigo-600 text-white hover:bg-indigo-700
                         disabled:bg-gray-200 disabled:text-gray-400
                         disabled:cursor-not-allowed transition-colors'
            >
              <ArrowUp className='w-4 h-4' strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
