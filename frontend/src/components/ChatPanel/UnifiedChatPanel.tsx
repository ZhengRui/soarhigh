'use client';

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  AlertTriangle,
  ArrowUp,
  Check,
  Loader2,
  RotateCcw,
  Route,
  Square,
  Wrench,
} from 'lucide-react';
import { ChatMarkdown } from './ChatMarkdown';
import { ChatError, ErrorBanner } from './ErrorBanner';
import { ThinkingBlock } from './ThinkingBlock';
import { useMeetingAgentRevert } from './useMeetingAgentRevert';
import { useUnifiedAgentTurn } from './useUnifiedAgentTurn';
import {
  AgendaSnapshot,
  AgentTurnEvent,
  ChatMessage,
  RouterDecision,
} from './types';

function formatToolArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => {
      let val: string;
      if (typeof v === 'string') val = JSON.stringify(v);
      else if (v === null || v === undefined) val = 'null';
      else if (Array.isArray(v)) val = JSON.stringify(v);
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

function routeLabel(decision: RouterDecision): string {
  if (decision.route === 'handoff') return 'Handoff';
  if (decision.route === 'clarify') return 'Clarify';
  if (decision.route === 'refuse') return 'Refused';
  if (decision.agent_kind === 'statistics') return 'Statistics';
  if (decision.agent_kind === 'meeting') return 'Meeting';
  return 'Router';
}

function routePalette(decision: RouterDecision): string {
  if (decision.route === 'handoff') {
    return 'bg-violet-50 border-violet-200 text-violet-800';
  }
  if (decision.route === 'clarify' || decision.route === 'refuse') {
    return 'bg-amber-50 border-amber-200 text-amber-800';
  }
  if (decision.agent_kind === 'statistics') {
    return 'bg-sky-50 border-sky-200 text-sky-800';
  }
  return 'bg-emerald-50 border-emerald-200 text-emerald-800';
}

export function UnifiedChatPanel({
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
  const lastSentRef = useRef<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const forceScrollRef = useRef(false);

  const NEAR_BOTTOM_PX = 80;
  const isNearBottom = (el: HTMLElement) =>
    el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (forceScrollRef.current || isNearBottom(el) || messages.length <= 2) {
      el.scrollTop = el.scrollHeight;
      forceScrollRef.current = false;
    }
  }, [messages]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      if (isNearBottom(el)) {
        el.scrollTop = el.scrollHeight;
      }
    });
    ro.observe(el);
    const inner = el.firstElementChild;
    if (inner) ro.observe(inner);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (el.offsetParent === null) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const onEvent = useCallback(
    (ev: AgentTurnEvent) => {
      if (ev.type === 'tool_call_end' && ev.data.agenda_after) {
        onAgendaAfter(ev.data.agenda_after);
      } else if (ev.type === 'done' && ev.data.final_agenda) {
        onAgendaAfter(ev.data.final_agenda);
      }

      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== 'assistant') return prev;

        if (ev.type === 'error') {
          const isEmpty =
            !last.content &&
            !last.thinking &&
            !(last.toolCalls && last.toolCalls.length);
          return isEmpty ? prev.slice(0, -1) : prev;
        }

        const next = [...prev];
        const msg = { ...last };
        if (ev.type === 'router_decision') {
          msg.routerDecision = ev.data.decision;
        }
        if (ev.type === 'handoff_proposal') {
          msg.handoffProposal = ev.data;
        }
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
          msg.canRevert = Boolean(ev.data.final_agenda && !ev.data.router_only);
          const prevMsg = next[next.length - 2];
          if (prevMsg && prevMsg.role === 'user' && msg.canRevert) {
            next[next.length - 2] = {
              ...prevMsg,
              seq: ev.data.seq,
              canRevert: true,
            };
          }
        }
        if (ev.type === 'cancelled') {
          msg.cancelled = true;
        }
        next[next.length - 1] = msg;
        return next;
      });

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

  const { send, stop } = useUnifiedAgentTurn({ onEvent });
  const revert = useMeetingAgentRevert();

  const handleRevert = useCallback(
    async (targetSeq: number, userContent: string) => {
      if (loading) return;
      try {
        const { agenda } = await revert(sessionKey, targetSeq);
        setMessages((prev) => {
          const cutIdx = prev.findIndex(
            (m) => m.seq !== undefined && m.seq >= targetSeq
          );
          return cutIdx === -1 ? prev : prev.slice(0, cutIdx);
        });
        onAgendaAfter(agenda);
        setInput(userContent);
        textareaRef.current?.focus();
      } catch (e) {
        console.error('revert failed', e);
      }
    },
    [loading, revert, sessionKey, onAgendaAfter]
  );

  const runTurn = useCallback(
    async (message: string, includeUserBubble: boolean) => {
      const asstMsg: ChatMessage = {
        id: uuid(),
        role: 'assistant',
        content: '',
        toolCalls: [],
      };
      forceScrollRef.current = true;
      if (includeUserBubble) {
        const userMsg: ChatMessage = {
          id: uuid(),
          role: 'user',
          content: message,
        };
        setMessages((m) => [...m, userMsg, asstMsg]);
      } else {
        setMessages((m) => [...m, asstMsg]);
      }
      lastSentRef.current = message;
      setError(null);
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

  const sendMessage = useCallback(
    (message: string) => runTurn(message, true),
    [runTurn]
  );

  const submit = () => {
    if (!input.trim() || loading) return;
    const message = input;
    setInput('');
    void sendMessage(message);
  };

  const handleRetry = useCallback(() => {
    if (!lastSentRef.current || loading) return;
    void runTurn(lastSentRef.current, false);
  }, [loading, runTurn]);

  const placeholderHelp = useMemo(
    () => (
      <div className='text-xs text-gray-400 text-center py-10 leading-relaxed'>
        Ask about this agenda or historical stats.
        <br />
        e.g. &ldquo;set Timer to Joyce&rdquo;,
        <br />
        &ldquo;who won Best Evaluator most?&rdquo;.
      </div>
    ),
    []
  );

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
        {messages.length === 0 && placeholderHelp}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex items-center gap-1.5 group ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {m.role === 'user' && m.seq !== undefined && m.canRevert && (
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
              {m.role === 'assistant' && m.routerDecision && (
                <div
                  title={m.routerDecision.reason}
                  className={`inline-flex items-center gap-1 text-[11px] font-mono px-2 py-1 rounded-md border mb-1.5 ${routePalette(
                    m.routerDecision
                  )}`}
                >
                  <Route className='w-3 h-3 shrink-0 opacity-70' />
                  <span>{routeLabel(m.routerDecision)}</span>
                </div>
              )}
              {m.role === 'assistant' && m.handoffProposal && (
                <div
                  title={m.handoffProposal.intent}
                  className='flex flex-col gap-1 text-[11px] font-mono px-2 py-1.5 rounded-md border mb-1.5 bg-violet-50 border-violet-200 text-violet-800'
                >
                  <div className='flex items-center gap-1.5'>
                    <Route className='w-3 h-3 shrink-0 opacity-70' />
                    <span className='font-semibold'>
                      {m.handoffProposal.source_agent} →{' '}
                      {m.handoffProposal.target_agent}
                    </span>
                    {m.handoffProposal.requires_confirmation && (
                      <span className='ml-auto text-[10px] uppercase tracking-wide opacity-70'>
                        confirm
                      </span>
                    )}
                  </div>
                  <div className='text-[10px] opacity-75'>
                    facts {m.handoffProposal.facts?.length ?? 0} · refs{' '}
                    {m.handoffProposal.references?.length ?? 0}
                  </div>
                </div>
              )}
              {m.role === 'assistant' && m.thinking && (
                <ThinkingBlock
                  content={m.thinking}
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
                submit();
              }
            }}
            placeholder='Ask or edit…'
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
