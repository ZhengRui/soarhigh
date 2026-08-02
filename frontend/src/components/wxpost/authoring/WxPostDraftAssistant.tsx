'use client';

import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { createPortal } from 'react-dom';

import type { WorkspaceDraftSession } from '@/utils/wxpostWorkspace';

import type { DraftMode } from './WxPostDraftControls';
import { WxPostHermesPanel } from './WxPostHermesPanel';
import type {
  CompletedDraftProgress,
  DraftProgressActivity,
} from './useWxPostDraftAssistant';
import { WorkspaceConflictDialog } from './WorkspaceConflictDialog';

type AssistantProps = {
  active: boolean;
  mode: DraftMode;
  portalReady: boolean;
  mobileOpen: boolean;
  session: WorkspaceDraftSession | null;
  sessionStatus: 'connecting' | 'online' | 'unavailable';
  chatPending: boolean;
  resetPending: boolean;
  progress: DraftProgressActivity[];
  completedProgress: CompletedDraftProgress[];
  selectedText: string | null;
  message: string;
  dirty: boolean;
  onMobileOpenChange: (open: boolean) => void;
  onClearSelection: () => void;
  onMessageChange: (message: string) => void;
  onSend: () => void;
  onReset: () => Promise<boolean>;
};

export function WxPostDraftAssistant(props: AssistantProps) {
  const [resetConfirming, setResetConfirming] = useState(false);
  if (props.mode !== 'edit') return null;
  const panelProps = {
    session: props.session,
    sessionStatus: props.sessionStatus,
    chatPending: props.chatPending,
    progress: props.progress,
    completedProgress: props.completedProgress,
    selectedText: props.selectedText,
    message: props.message,
    dirty: props.dirty,
    onClearSelection: props.onClearSelection,
    onMessageChange: props.onMessageChange,
    onSend: props.onSend,
    onNewConversationRequest: () => setResetConfirming(true),
  };

  const confirmReset = async () => {
    if (await props.onReset()) setResetConfirming(false);
  };

  return (
    <>
      <aside
        className='sticky top-24 hidden h-[calc(100dvh-7rem)] min-h-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:block'
        data-testid='desktop-hermes-panel'
      >
        <WxPostHermesPanel
          {...panelProps}
          mobile={false}
          onClose={() => props.onMobileOpenChange(false)}
        />
      </aside>

      {props.portalReady &&
        props.active &&
        createPortal(
          <>
            {!props.mobileOpen && (
              <button
                type='button'
                className='fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-5 z-[70] grid h-12 w-12 place-items-center rounded-full border border-blue-700 bg-blue-600 text-white shadow-[0_10px_28px_rgba(37,99,235,0.32)] transition hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300 lg:hidden'
                aria-label='Open Draft Assistant'
                onClick={() => props.onMobileOpenChange(true)}
                data-testid='open-mobile-hermes'
              >
                <Sparkles className='h-5 w-5' aria-hidden='true' />
              </button>
            )}

            {props.mobileOpen && (
              <div
                className='fixed inset-0 z-[80] lg:hidden'
                role='dialog'
                aria-modal='true'
                aria-label='Draft Assistant'
                data-testid='mobile-hermes-dialog'
              >
                <button
                  type='button'
                  className='absolute inset-0 bg-slate-950/35'
                  aria-label='Dismiss Draft Assistant'
                  onClick={() => props.onMobileOpenChange(false)}
                />
                <div
                  className='absolute inset-x-0 bottom-0 flex h-[min(78dvh,38rem)] flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-[0_-16px_40px_rgba(15,23,42,0.18)] sm:inset-y-4 sm:left-auto sm:right-4 sm:h-auto sm:w-[min(26rem,calc(100vw-2rem))] sm:rounded-2xl sm:shadow-2xl'
                  data-testid='mobile-hermes-sheet'
                >
                  <WxPostHermesPanel
                    {...panelProps}
                    mobile
                    onClose={() => props.onMobileOpenChange(false)}
                  />
                </div>
              </div>
            )}
          </>,
          globalThis.document.body
        )}
      {props.portalReady && resetConfirming && (
        <WorkspaceConflictDialog
          title='Start a new conversation?'
          error={null}
          pending={props.resetPending}
          testId='draft-session-reset-dialog'
          keepLabel='Cancel'
          loadLabel='Start new conversation'
          pendingLabel='Starting…'
          onKeepCurrent={() => setResetConfirming(false)}
          onLoadLatest={() => void confirmReset()}
        >
          This clears the Draft Assistant chat. Your workspace, Materials, and
          saved Draft will not change.
        </WorkspaceConflictDialog>
      )}
    </>
  );
}
