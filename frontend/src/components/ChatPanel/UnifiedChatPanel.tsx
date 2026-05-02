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
  Paperclip,
  RotateCcw,
  Route,
  Square,
  Wrench,
  X,
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
  MessagePart,
  RouterDecision,
} from './types';

// Coalesce consecutive same-kind streamed chunks (text/text or
// thinking/thinking) into the trailing part so a 50-chunk text stream
// renders as one markdown block, not 50 fragments. Tool parts always
// push fresh — see reducer in onEvent.
function appendStreamingChunk(
  parts: MessagePart[] | undefined,
  kind: 'text' | 'thinking',
  chunk: string
): MessagePart[] {
  const list = parts || [];
  const last = list[list.length - 1];
  if (last && last.kind === kind) {
    return [...list.slice(0, -1), { ...last, content: last.content + chunk }];
  }
  return [...list, { kind, content: chunk }];
}

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
  if (decision.route === 'clarify') return 'Clarify';
  if (decision.route === 'refuse') return 'Refused';
  if (decision.route === 'direct_answer') return 'Router';
  if (decision.agent_kind === 'statistics') return 'Statistics';
  if (decision.agent_kind === 'meeting') return 'Meeting';
  return 'Router';
}

function routePalette(decision: RouterDecision): string {
  if (decision.route === 'clarify' || decision.route === 'refuse') {
    return 'bg-amber-50 border-amber-200 text-amber-800';
  }
  if (decision.route === 'direct_answer') {
    return 'bg-gray-50 border-gray-200 text-gray-700';
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
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const lastSentRef = useRef<string>('');
  const lastImageRef = useRef<File | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const forceScrollRef = useRef(false);
  const pendingImageUrl = useMemo(
    () => (pendingImage ? URL.createObjectURL(pendingImage) : null),
    [pendingImage]
  );

  useEffect(() => {
    return () => {
      if (pendingImageUrl) URL.revokeObjectURL(pendingImageUrl);
    };
  }, [pendingImageUrl]);

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
        if (ev.type === 'thinking') {
          msg.thinking = (msg.thinking || '') + ev.data.chunk;
          msg.parts = appendStreamingChunk(
            msg.parts,
            'thinking',
            ev.data.chunk
          );
        }
        if (ev.type === 'assistant_text') {
          msg.content = (msg.content || '') + ev.data.chunk;
          msg.parts = appendStreamingChunk(msg.parts, 'text', ev.data.chunk);
        }
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
          msg.parts = [
            ...(msg.parts || []),
            { kind: 'tool', toolCallId: ev.data.id },
          ];
        }
        if (ev.type === 'tool_call_end') {
          const status = ev.data.status === 'retry' ? 'retry' : 'ok';
          msg.toolCalls = (msg.toolCalls || []).map((tc) =>
            tc.id === ev.data.id
              ? { ...tc, status, result: ev.data.result }
              : tc
          );
          // `parts` intentionally NOT touched — the tool's position in
          // the timeline was fixed at start; only its rendered status
          // updates via the toolCalls lookup.
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
    async (message: string, image: File | null, includeUserBubble: boolean) => {
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
          content: message || '[Image attached]',
        };
        setMessages((m) => [...m, userMsg, asstMsg]);
      } else {
        setMessages((m) => [...m, asstMsg]);
      }
      lastSentRef.current = message;
      lastImageRef.current = image;
      setError(null);
      setLoading(true);
      try {
        await send({
          session_id: sessionKey,
          user_message: message,
          agenda_snapshot: agendaSnapshot,
          image,
        });
      } catch {
        setLoading(false);
      }
    },
    [send, sessionKey, agendaSnapshot]
  );

  const sendMessage = useCallback(
    (message: string, image: File | null) => runTurn(message, image, true),
    [runTurn]
  );

  const submit = () => {
    if ((!input.trim() && !pendingImage) || loading) return;
    const message = input;
    const image = pendingImage;
    setInput('');
    setPendingImage(null);
    void sendMessage(message, image);
  };

  const handleRetry = useCallback(() => {
    if ((!lastSentRef.current && !lastImageRef.current) || loading) return;
    void runTurn(lastSentRef.current, lastImageRef.current, false);
  }, [loading, runTurn]);

  const handleAttach = () => fileInputRef.current?.click();
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      alert('Only jpg / png / webp accepted');
      e.target.value = '';
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert('Image must be < 5 MB');
      e.target.value = '';
      return;
    }
    setPendingImage(file);
    e.target.value = '';
  };

  const placeholderHelp = useMemo(
    () => (
      <div className='text-xs text-gray-400 text-center py-10 leading-relaxed space-y-3 px-4'>
        <div>Try:</div>
        <div className='space-y-1'>
          <div>&ldquo;clone a meeting from #451&rdquo;</div>
          <div>&ldquo;让 Helen 做 Timer&rdquo;</div>
          <div>
            &ldquo;when was last meeting Joyce as the meeting manager&rdquo;
          </div>
          <div>&ldquo;按今年会员参会次数排序前三名是哪些人&rdquo;</div>
        </div>
        <div>…and more.</div>
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
              {m.role === 'assistant' ? (
                m.parts && m.parts.length > 0 ? (
                  <div className='flex flex-col gap-1.5'>
                    {m.parts.map((part, idx) => {
                      const isLast = idx === m.parts!.length - 1;
                      if (part.kind === 'thinking') {
                        return (
                          <ThinkingBlock
                            key={`p${idx}`}
                            content={part.content}
                            streaming={isLast && !m.seq}
                          />
                        );
                      }
                      if (part.kind === 'text') {
                        return (
                          <ChatMarkdown key={`p${idx}`} source={part.content} />
                        );
                      }
                      // kind === 'tool' — look up authoritative status
                      // from msg.toolCalls so `tool_call_end` updates
                      // reflect without disturbing render order.
                      const tc = m.toolCalls?.find(
                        (t) => t.id === part.toolCallId
                      );
                      if (!tc) return null;
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
                ) : (
                  <div className='whitespace-pre-wrap'>…</div>
                )
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
        {pendingImage && pendingImageUrl && (
          <div className='mb-2 flex items-center gap-2 px-2 py-1 rounded-md bg-gray-100 text-xs text-gray-700'>
            <div
              aria-label='attached image preview'
              className='h-8 w-8 shrink-0 rounded bg-cover bg-center'
              style={{ backgroundImage: `url(${pendingImageUrl})` }}
            />
            <span className='truncate flex-1 min-w-0'>{pendingImage.name}</span>
            <button
              type='button'
              onClick={() => setPendingImage(null)}
              aria-label='Remove image'
              className='shrink-0 h-6 w-6 flex items-center justify-center rounded-full hover:bg-gray-200'
            >
              <X className='w-3.5 h-3.5' />
            </button>
          </div>
        )}
        <div
          className='flex items-center gap-1.5 rounded-2xl border border-gray-200
                     bg-gray-50 pl-2 pr-1 py-1
                     focus-within:border-gray-300 focus-within:bg-white transition-colors'
        >
          <input
            ref={fileInputRef}
            type='file'
            accept='image/jpeg,image/png,image/webp'
            className='hidden'
            onChange={handleFileChange}
          />
          <button
            type='button'
            onClick={handleAttach}
            aria-label='Attach image'
            disabled={loading}
            className='shrink-0 flex items-center justify-center h-8 w-8 rounded-full
                       text-gray-500 hover:text-gray-800 hover:bg-gray-100
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors'
          >
            <Paperclip className='w-4 h-4' />
          </button>
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
            placeholder='Chat an agenda or ask about stats'
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
              disabled={!input.trim() && !pendingImage}
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
