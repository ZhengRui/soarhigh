'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
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

  useEffect(() => {
    // Auto-scroll to bottom on any message change
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

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
    <div className='flex flex-col h-full min-h-0'>
      <div
        ref={scrollRef}
        className='flex-1 min-h-0 overflow-y-auto p-3 space-y-2'
      >
        {messages.length === 0 && (
          <div className='text-xs text-gray-400 text-center py-6'>
            Ask me to edit the agenda — e.g. &ldquo;change SAA to Joyce&rdquo;,
            &ldquo;move Timer 2 min later&rdquo;.
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === 'user' ? 'text-right' : 'text-left'}
          >
            <div
              className={`inline-block max-w-[85%] px-3 py-2 rounded-lg ${
                m.role === 'user' ? 'bg-blue-100' : 'bg-gray-100'
              }`}
            >
              {m.role === 'assistant' &&
                m.toolCalls &&
                m.toolCalls.length > 0 && (
                  <div className='text-xs text-gray-500 mb-1'>
                    {m.toolCalls.map((tc) => (
                      <span key={tc.id} className='mr-2'>
                        {tc.pending ? '🛠 ' : '🛠 ✓ '}
                        {tc.name}
                      </span>
                    ))}
                  </div>
                )}
              <div className='whitespace-pre-wrap text-sm'>
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
      <div className='border-t p-2 flex gap-2'>
        <input
          className='flex-1 border rounded px-2 py-1 text-sm disabled:bg-gray-50'
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder='Type a message…'
          disabled={loading}
        />
        {loading ? (
          <button
            onClick={stop}
            className='px-3 py-1 text-sm bg-red-500 text-white rounded hover:bg-red-600'
          >
            Stop
          </button>
        ) : (
          <button
            onClick={submit}
            className='px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600'
            disabled={!input.trim()}
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
