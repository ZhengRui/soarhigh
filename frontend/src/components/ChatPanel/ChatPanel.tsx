'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowUp,
  Check,
  Loader2,
  RotateCcw,
  Square,
  Wrench,
} from 'lucide-react';
import { ChatMarkdown } from './ChatMarkdown';
import { ChatError, ErrorBanner } from './ErrorBanner';
import { ThinkingBlock } from './ThinkingBlock';
import { useMeetingAgentRevert } from './useMeetingAgentRevert';
import { useMeetingAgentTurn } from './useMeetingAgentTurn';
import { AgendaSnapshot, AgentTurnEvent, ChatMessage } from './types';

function formatToolArgs(args: Record<string, unknown>): string {
  // key=value AND alphabetical key order so the display stays consistent
  // across calls regardless of which order the model emitted the keys in.
  return Object.entries(args)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => {
      let val: string;
      if (typeof v === 'string') val = JSON.stringify(v);
      else if (v === null || v === undefined) val = 'null';
      else val = String(v);
      return `${k}=${val}`;
    })
    .join(', ');
}

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
  const [error, setError] = useState<ChatError | null>(null);
  // Holds the last user message actually sent. Needed so the Retry button
  // can re-submit without the user retyping. Reset on any new send.
  const lastSentRef = useRef<string>('');
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
      // Propagate agenda updates to the parent FIRST, outside the setMessages
      // updater. Calling a parent's setState from inside another component's
      // updater function triggers React's "setState during render" warning.
      if (ev.type === 'tool_call_end') {
        onAgendaAfter(ev.data.agenda_after);
      } else if (ev.type === 'done') {
        onAgendaAfter(ev.data.final_agenda);
      }

      // Then update our own local message state (pure updater, no side effects).
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== 'assistant') return prev;

        // If the turn errored before producing ANY output (no text, no
        // thinking, no tool calls), drop the empty assistant bubble. The
        // error banner at the top of the panel already communicates the
        // failure; the empty "…" placeholder is just noise.
        if (ev.type === 'error') {
          const isEmpty =
            !last.content &&
            !last.thinking &&
            !(last.toolCalls && last.toolCalls.length);
          return isEmpty ? prev.slice(0, -1) : prev;
        }

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
              status: 'pending',
            },
          ];
        }
        if (ev.type === 'tool_call_end') {
          const status = ev.data.status === 'retry' ? 'retry' : 'ok';
          msg.toolCalls = (msg.toolCalls || []).map((tc) =>
            tc.id === ev.data.id
              ? { ...tc, status, result: ev.data.result }
              : tc
          );
        }
        if (ev.type === 'done') {
          msg.seq = ev.data.seq;
          // Also tag the paired USER message (the one right before this
          // assistant bubble) with the same seq. That's what the ↺ icon
          // targets: reverting via a user bubble rewinds to BEFORE that
          // turn ran, which matches the user's mental model.
          const prev = next[next.length - 2];
          if (prev && prev.role === 'user') {
            next[next.length - 2] = { ...prev, seq: ev.data.seq };
          }
        }
        if (ev.type === 'cancelled') {
          msg.cancelled = true;
        }
        next[next.length - 1] = msg;
        return next;
      });

      // Errors surface as a top-of-panel banner, not inline on the bubble —
      // easier to spot, and the banner carries the Retry affordance.
      if (ev.type === 'error') {
        setError({
          reason: ev.data.reason,
          recoverable: ev.data.recoverable,
          message: ev.data.message,
        });
      }
      if (ev.type === 'done' || ev.type === 'error' || ev.type === 'cancelled')
        setLoading(false);
    },
    [onAgendaAfter]
  );

  const { send, stop } = useMeetingAgentTurn({ onEvent });
  const revert = useMeetingAgentRevert();

  const handleRevert = useCallback(
    async (targetSeq: number, userContent: string) => {
      if (loading) return;
      try {
        const { agenda } = await revert(sessionKey, targetSeq);
        // Drop any messages whose seq is >= targetSeq. Messages without a
        // seq (currently streaming, or the user's just-typed message that
        // hasn't completed yet) are also dropped if they trail the cut line.
        setMessages((prev) => {
          const cutIdx = prev.findIndex(
            (m) => m.seq !== undefined && m.seq >= targetSeq
          );
          return cutIdx === -1 ? prev : prev.slice(0, cutIdx);
        });
        onAgendaAfter(agenda);
        // Repopulate the textarea with the reverted message so the user can
        // tweak and resend without retyping — same UX as chat-agenda.
        setInput(userContent);
        textareaRef.current?.focus();
      } catch (e) {
        // Non-fatal: surface to console so the UI doesn't freeze. The
        // backend may return 404 if the turn was already deleted (e.g.
        // duplicate click while the first revert is in flight).
        console.error('revert failed', e);
      }
    },
    [loading, revert, sessionKey, onAgendaAfter]
  );

  const sendMessage = useCallback(
    async (message: string) => {
      const userMsg: ChatMessage = {
        id: uuid(),
        role: 'user',
        content: message,
      };
      const asstMsg: ChatMessage = {
        id: uuid(),
        role: 'assistant',
        content: '',
        toolCalls: [],
      };
      setMessages((m) => [...m, userMsg, asstMsg]);
      lastSentRef.current = message;
      setError(null); // clear any prior banner — we're making a new attempt
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
    },
    [send, sessionKey, agendaSnapshot]
  );

  const submit = () => {
    if (!input.trim() || loading) return;
    const message = input;
    setInput('');
    void sendMessage(message);
  };

  const handleRetry = useCallback(() => {
    if (!lastSentRef.current || loading) return;
    void sendMessage(lastSentRef.current);
  }, [loading, sendMessage]);

  return (
    <div className='flex flex-col h-full min-h-0 bg-white'>
      {error && (
        <ErrorBanner
          error={error}
          onRetry={error.recoverable ? handleRetry : undefined}
          onDismiss={() => setError(null)}
        />
      )}
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
            className={`flex items-center gap-1.5 group ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {m.role === 'user' && m.seq !== undefined && (
              <button
                type='button'
                onClick={() => handleRevert(m.seq!, m.content)}
                disabled={loading}
                title='Revert to the state before this turn'
                className='shrink-0 h-6 w-6 flex items-center justify-center rounded-full
                           text-gray-400 hover:text-gray-700 hover:bg-gray-100
                           disabled:opacity-30 disabled:cursor-not-allowed
                           opacity-0 group-hover:opacity-100 transition-opacity'
              >
                <RotateCcw className='w-3.5 h-3.5' />
              </button>
            )}
            <div
              className={`max-w-[85%] px-3 py-2 rounded-lg text-sm text-left ${
                m.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {m.role === 'assistant' && m.thinking && (
                <ThinkingBlock
                  content={m.thinking}
                  // If content hasn't started AND no tools have completed,
                  // thinking is likely still streaming (Gemini emits thinking
                  // before either). Rough heuristic — a perfect signal would
                  // require a thinking_end SSE event.
                  streaming={
                    !m.content &&
                    !(
                      m.toolCalls &&
                      m.toolCalls.some((t) => t.status !== 'pending')
                    )
                  }
                />
              )}
              {m.role === 'assistant' &&
                m.toolCalls &&
                m.toolCalls.length > 0 && (
                  <div className='flex flex-col gap-1 mb-1.5'>
                    {m.toolCalls.map((tc) => {
                      const argsStr = formatToolArgs(tc.args);
                      const palette =
                        tc.status === 'pending'
                          ? 'bg-sky-50 border-sky-200 text-sky-800'
                          : tc.status === 'retry'
                            ? 'bg-amber-50 border-amber-300 text-amber-800'
                            : 'bg-emerald-50 border-emerald-200 text-emerald-800';
                      return (
                        <div
                          key={tc.id}
                          title={`${tc.name}(${argsStr})${tc.status === 'retry' ? ' — refused' : ''}`}
                          className={`flex items-center gap-1.5 text-[11px] font-mono px-2 py-1 rounded-md border cursor-default ${palette}`}
                        >
                          <Wrench className='w-3 h-3 shrink-0 opacity-70' />
                          <span className='font-semibold shrink-0'>
                            {tc.name}
                          </span>
                          <span className='flex-1 min-w-0 truncate opacity-75'>
                            ({argsStr})
                          </span>
                          <span className='shrink-0 pl-0.5'>
                            {tc.status === 'pending' ? (
                              <Loader2 className='w-3 h-3 animate-spin' />
                            ) : tc.status === 'retry' ? (
                              <AlertTriangle
                                className='w-3 h-3'
                                strokeWidth={2.5}
                              />
                            ) : (
                              <Check className='w-3 h-3' strokeWidth={3} />
                            )}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              {m.role === 'assistant' ? (
                m.content ? (
                  <ChatMarkdown source={m.content} />
                ) : !(m.toolCalls && m.toolCalls.length) ? (
                  <div className='whitespace-pre-wrap'>…</div>
                ) : null
              ) : (
                <div className='whitespace-pre-wrap'>{m.content}</div>
              )}
              {m.cancelled && (
                <div className='text-gray-400 italic text-[11px] mt-1'>
                  [Request cancelled]
                </div>
              )}
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
