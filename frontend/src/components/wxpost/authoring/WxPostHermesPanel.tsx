'use client';

import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useRef,
  type KeyboardEvent,
  type UIEvent,
} from 'react';
import {
  ArrowUp,
  Check,
  ChevronDown,
  CircleX,
  Loader2,
  Sparkles,
  X,
} from 'lucide-react';

import type { WorkspaceDraftConversation } from '@/utils/wxpostWorkspace';

import type {
  DraftAssistantStatus,
  DraftProgressActivity,
} from './useWxPostDraftAssistant';

function ActivityDetails({ step }: { step: DraftProgressActivity }) {
  if (!step.toolName && !step.operationNames?.length) return null;
  return (
    <span className='ml-1.5 inline-flex min-w-0 max-w-full flex-wrap items-center gap-1 align-middle'>
      {step.operationNames?.map((operationName) => (
        <code
          key={operationName}
          className='max-w-full break-all rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] whitespace-normal text-blue-700'
        >
          {operationName}
        </code>
      ))}
      {step.toolName && (
        <code className='max-w-full break-all rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] whitespace-normal text-slate-500'>
          {step.toolName}
        </code>
      )}
    </span>
  );
}

function CompletedProgressDisclosure({
  steps,
}: {
  steps: DraftProgressActivity[];
}) {
  const failedCount = steps.filter((step) => step.failed).length;
  const summary =
    failedCount > 0
      ? `${steps.length} ${steps.length === 1 ? 'step' : 'steps'} finished · ${failedCount} failed`
      : `${steps.length} ${steps.length === 1 ? 'step' : 'steps'} completed`;
  return (
    <details className='group min-w-0 max-w-full text-xs text-slate-500'>
      <summary className='flex max-w-full w-fit cursor-pointer list-none items-center gap-1.5 rounded-lg px-2 py-1 hover:bg-slate-100'>
        {failedCount > 0 ? (
          <CircleX className='h-3.5 w-3.5 text-red-600' />
        ) : (
          <Check className='h-3.5 w-3.5 text-emerald-600' />
        )}
        {summary}
        <ChevronDown className='h-3.5 w-3.5 transition group-open:rotate-180' />
      </summary>
      <div className='mt-1 grid min-w-0 max-w-full gap-1 pl-2'>
        {steps.map((step) => (
          <p
            key={step.activityId}
            className='m-0 flex min-w-0 max-w-full items-start gap-2 leading-5'
          >
            {step.failed ? (
              <CircleX className='mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600' />
            ) : (
              <Check className='mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600' />
            )}
            <span className='min-w-0 max-w-full break-words [overflow-wrap:anywhere]'>
              {step.label}
              <ActivityDetails step={step} />
            </span>
          </p>
        ))}
      </div>
    </details>
  );
}

export function WxPostHermesPanel({
  mobile,
  conversation,
  assistantStatus,
  chatPending,
  progress,
  selectedText,
  message,
  dirty,
  onClose,
  onClearSelection,
  onMessageChange,
  onSend,
  onNewConversationRequest,
}: {
  mobile: boolean;
  conversation: WorkspaceDraftConversation | null;
  assistantStatus: DraftAssistantStatus;
  chatPending: boolean;
  progress: DraftProgressActivity[];
  selectedText: string | null;
  message: string;
  dirty: boolean;
  onClose: () => void;
  onClearSelection: () => void;
  onMessageChange: (message: string) => void;
  onSend: () => void;
  onNewConversationRequest: () => void;
}) {
  const historyRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const historySizeRef = useRef<{
    clientHeight: number;
    scrollHeight: number;
  } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messages = conversation?.messages ?? [];
  const progressState = progress
    .map(
      ({ activityId, label, toolName, operationNames, completed, failed }) =>
        `${activityId}:${label}:${toolName ?? ''}:${operationNames?.join(',') ?? ''}:${failed ? 'failed' : completed ? 'done' : 'active'}`
    )
    .join('|');

  useLayoutEffect(() => {
    const history = historyRef.current;
    if (!history) return;
    if (autoScrollRef.current) history.scrollTop = history.scrollHeight;
  }, [chatPending, messages.length, progressState]);

  useEffect(() => {
    const history = historyRef.current;
    if (!history) return;
    const observer = new ResizeObserver(() => {
      const previousSize = historySizeRef.current;
      const wasAtBottomBeforeResize = previousSize
        ? previousSize.scrollHeight -
            history.scrollTop -
            previousSize.clientHeight <
          24
        : autoScrollRef.current;
      if (autoScrollRef.current || wasAtBottomBeforeResize) {
        autoScrollRef.current = true;
        history.scrollTop = history.scrollHeight;
      }
      historySizeRef.current = {
        clientHeight: history.clientHeight,
        scrollHeight: history.scrollHeight,
      };
    });
    observer.observe(history);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [message]);

  const submitMessage = () => {
    const request = message.trim();
    if (!request || chatPending) return;
    if (request === '/new') {
      onNewConversationRequest();
      return;
    }
    if (dirty) return;
    onSend();
  };

  const handleMessageKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== 'Enter' ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    ) {
      return;
    }
    event.preventDefault();
    submitMessage();
  };

  const handleHistoryScroll = (event: UIEvent<HTMLDivElement>) => {
    const history = event.currentTarget;
    autoScrollRef.current =
      history.scrollHeight - history.scrollTop - history.clientHeight < 24;
  };

  const hasActiveActivity = progress.some(
    (activity) => !activity.completed && !activity.failed
  );

  return (
    <div className='flex h-full min-h-0 min-w-0 max-w-full flex-col overflow-hidden bg-white'>
      <div className='flex shrink-0 items-start justify-between border-b border-slate-200 px-4 py-3'>
        <div>
          <div className='flex items-center gap-2'>
            <Sparkles className='h-4 w-4 text-blue-600' aria-hidden='true' />
            <h2 className='m-0 text-sm font-bold text-slate-900'>
              Draft Assistant
            </h2>
          </div>
          <p className='mb-0 mt-1 text-[11px] text-slate-500'>
            Answers questions and saves edits as new Draft versions.
          </p>
        </div>
        <div className='flex items-center gap-2'>
          <span
            className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
              assistantStatus === 'ready'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            {assistantStatus === 'connecting'
              ? 'Connecting…'
              : assistantStatus === 'ready'
                ? 'Ready'
                : 'Unavailable'}
          </span>
          {mobile && (
            <button
              type='button'
              className='grid h-8 w-8 place-items-center rounded-full border border-slate-200 text-slate-500'
              aria-label='Close Draft Assistant'
              onClick={onClose}
            >
              <X className='h-4 w-4' />
            </button>
          )}
        </div>
      </div>
      <div
        ref={historyRef}
        className='grid min-h-0 min-w-0 max-w-full flex-1 content-start gap-3 overflow-x-hidden overflow-y-auto bg-slate-50/60 p-4'
        aria-live='polite'
        data-testid={
          mobile ? 'mobile-draft-chat-history' : 'draft-chat-history'
        }
        onScroll={handleHistoryScroll}
      >
        {messages.length === 0 ? (
          <div className='grid min-h-44 place-content-center text-center text-sm text-slate-500'>
            <Sparkles className='mx-auto mb-2 h-5 w-5 text-blue-500' />
            Ask about the article or request a Draft edit.
          </div>
        ) : (
          messages.map((item, index) => {
            const isPendingMessage =
              chatPending &&
              item.role === 'user' &&
              index === messages.length - 1;
            return (
              <Fragment key={`${item.role}-${index}`}>
                {item.role === 'assistant' && Boolean(item.steps?.length) && (
                  <CompletedProgressDisclosure steps={item.steps ?? []} />
                )}
                <p
                  className={`m-0 max-w-[92%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-6 ${
                    item.role === 'user'
                      ? 'ml-auto rounded-br-md bg-blue-600 text-white'
                      : 'rounded-bl-md border border-slate-200 bg-white text-slate-700'
                  }`}
                >
                  {item.role === 'user' && item.selectedText && (
                    <span className='mb-1 block border-l-2 border-blue-200 pl-2 text-xs text-blue-100'>
                      “{item.selectedText}”
                    </span>
                  )}
                  <span>{item.text}</span>
                </p>
                {isPendingMessage && (
                  <div
                    className='grid min-w-0 max-w-full gap-1 px-2 py-1 text-xs text-slate-500'
                    data-testid='draft-assistant-progress'
                  >
                    {progress.map((activity) => {
                      return (
                        <p
                          key={activity.activityId}
                          className='m-0 flex min-w-0 max-w-full items-start gap-2 leading-5'
                        >
                          {activity.failed ? (
                            <CircleX
                              className='mt-0.5 h-4 w-4 shrink-0 text-red-600'
                              aria-label='Failed'
                            />
                          ) : activity.completed ? (
                            <Check className='mt-0.5 h-4 w-4 shrink-0 text-emerald-600' />
                          ) : (
                            <Loader2 className='mt-0.5 h-4 w-4 shrink-0 animate-spin' />
                          )}
                          <span className='min-w-0 max-w-full break-words [overflow-wrap:anywhere]'>
                            {activity.label}
                            <ActivityDetails step={activity} />
                          </span>
                        </p>
                      );
                    })}
                    {!hasActiveActivity && (
                      <p className='m-0 flex min-w-0 items-start gap-2 leading-5'>
                        <Loader2 className='mt-0.5 h-4 w-4 shrink-0 animate-spin' />
                        <span>
                          {progress.length > 0 ? 'Working…' : 'Thinking…'}
                        </span>
                      </p>
                    )}
                  </div>
                )}
              </Fragment>
            );
          })
        )}
      </div>
      <div
        className='shrink-0 border-t border-slate-200 bg-white p-3'
        data-testid={
          mobile ? 'mobile-draft-chat-composer' : 'draft-chat-composer'
        }
      >
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
            ref={textareaRef}
            className='block min-h-20 max-h-40 w-full resize-none overflow-y-auto border-0 bg-transparent p-1 text-sm outline-none'
            placeholder='Ask about or revise the Draft…'
            value={message}
            disabled={chatPending}
            onChange={(event) => onMessageChange(event.target.value)}
            onKeyDown={handleMessageKeyDown}
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
              aria-label='Send message'
              disabled={
                !message.trim() ||
                chatPending ||
                (dirty && message.trim() !== '/new')
              }
              title={
                dirty && message.trim() !== '/new'
                  ? 'Save local edits before asking the assistant.'
                  : undefined
              }
              onClick={submitMessage}
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
