'use client';

import {
  ArrowRight,
  Check,
  ChevronDown,
  Link2,
  Loader2,
  RefreshCw,
  Unlink,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  FOCUS_RING_CLASS,
  PANEL_CLASS,
  PANEL_HEADER_CLASS,
  PANEL_TITLE_CLASS,
  PRIMARY_BUTTON_CLASS,
} from './authoringStyles';
import { formatMeetingType } from './meetingLabels';
import type { MeetingOptionIF } from '@/interfaces';
import type { WorkspaceArticleType } from '@/utils/wxpostWorkspace';

import { ArticleTypePanel } from './ArticleTypePanel';

export type LinkedMeetingOption = MeetingOptionIF;

function formatDate(date: string) {
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return date;

  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(parsed);
}

function formatMeetingOption(meeting: LinkedMeetingOption) {
  return [
    meeting.no ? `#${meeting.no}` : null,
    formatMeetingType(meeting),
    formatDate(meeting.date),
    meeting.theme,
  ]
    .filter(Boolean)
    .join(' · ');
}

function MeetingSelect({
  meetings,
  selectedMeeting,
  isPending,
  hasError,
  isLoadingMore,
  hasMore,
  onChange,
  onLoadMore,
  onRetry,
  disabled,
}: {
  meetings: LinkedMeetingOption[];
  selectedMeeting: LinkedMeetingOption | null;
  isPending: boolean;
  hasError: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  onChange: (meetingId: string) => void;
  onLoadMore: () => void;
  onRetry: () => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const selectedMeetingId = selectedMeeting?.id ?? '';

  useEffect(() => {
    if (!open) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const placeholder = isPending
    ? 'Loading meetings…'
    : hasError
      ? 'Unable to load meetings'
      : meetings.length === 0
        ? 'No meetings available'
        : 'Choose a meeting or event';

  return (
    <div className='grid min-w-0 gap-2 max-[480px]:gap-1.5'>
      <span className='text-sm font-bold text-slate-700'>Meeting or event</span>
      <div className='relative min-w-0' ref={containerRef}>
        <button
          type='button'
          className='relative flex min-h-[50px] w-full min-w-0 max-w-full cursor-pointer items-center rounded-[11px] border border-[#cad5e4] bg-white py-0 pl-[15px] pr-12 text-left text-[15px] text-[#172033] outline-none hover:border-[#9fb1c8] focus-visible:border-blue-600 focus-visible:outline-none aria-expanded:border-blue-600 disabled:cursor-default disabled:bg-[#f7f9fc] disabled:text-[#8290a4] max-[480px]:!h-10 max-[480px]:!min-h-10 max-[480px]:pl-3 max-[480px]:pr-10 max-[480px]:text-sm'
          aria-haspopup='listbox'
          aria-expanded={open}
          aria-controls='wxpost-meeting-options'
          disabled={disabled || isPending || hasError || meetings.length === 0}
          onClick={() => setOpen((value) => !value)}
          data-testid='meeting-select-trigger'
        >
          <span className='min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap'>
            {selectedMeeting
              ? formatMeetingOption(selectedMeeting)
              : placeholder}
          </span>
          {isPending ? (
            <Loader2
              className='pointer-events-none absolute right-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 animate-spin text-slate-500'
              aria-hidden='true'
            />
          ) : (
            <ChevronDown
              className={`pointer-events-none absolute right-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-500 transition-transform duration-150 max-[480px]:right-3 max-[480px]:h-4 max-[480px]:w-4 ${
                open ? '-translate-y-1/2 rotate-180' : ''
              }`}
              aria-hidden='true'
            />
          )}
        </button>

        {open && (
          <div
            className='absolute inset-x-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-[11px] border border-[#cad5e4] bg-white shadow-xl'
            data-testid='meeting-select-options'
          >
            <div
              id='wxpost-meeting-options'
              className='max-h-[294px] overflow-y-auto p-[6px] max-[480px]:max-h-[260px] max-[480px]:p-1'
              role='listbox'
              aria-label='Meeting or event'
              onScroll={(event) => {
                const list = event.currentTarget;
                const distanceFromBottom =
                  list.scrollHeight - list.scrollTop - list.clientHeight;
                if (hasMore && !isLoadingMore && distanceFromBottom < 48) {
                  onLoadMore();
                }
              }}
            >
              {meetings.map((meeting) => {
                const selected = meeting.id === selectedMeetingId;
                return (
                  <button
                    key={meeting.id}
                    type='button'
                    role='option'
                    aria-selected={selected}
                    className={`flex min-h-10 w-full cursor-pointer items-center justify-between gap-[14px] rounded-[7px] border-0 px-[11px] py-[9px] text-left text-sm leading-[1.4] max-[480px]:min-h-9 max-[480px]:gap-2.5 max-[480px]:px-2.5 max-[480px]:py-2 max-[480px]:text-[13px] ${
                      selected
                        ? 'bg-[#e8efff] font-semibold text-blue-700'
                        : 'bg-transparent text-slate-700 hover:bg-slate-100'
                    }`}
                    onClick={() => {
                      onChange(meeting.id);
                      setOpen(false);
                    }}
                    data-testid={`meeting-option-${meeting.id}`}
                  >
                    <span className='min-w-0'>
                      {formatMeetingOption(meeting)}
                    </span>
                    {selected && (
                      <Check
                        className='h-[17px] w-[17px] shrink-0'
                        aria-hidden='true'
                      />
                    )}
                  </button>
                );
              })}
            </div>
            {isLoadingMore && (
              <div
                className='flex min-h-[38px] items-center justify-center gap-[7px] border-t border-slate-200 bg-slate-50 text-xs text-slate-500 [&_svg]:h-[14px] [&_svg]:w-[14px]'
                role='status'
              >
                <Loader2 className='animate-spin' aria-hidden='true' />
                Loading more meetings…
              </div>
            )}
          </div>
        )}
      </div>
      {hasError && (
        <button
          type='button'
          className='inline-flex w-fit items-center gap-2 text-sm font-semibold text-blue-700 hover:text-blue-800 focus-visible:outline-none focus-visible:underline [&_svg]:h-4 [&_svg]:w-4'
          onClick={onRetry}
          data-testid='retry-meeting-options'
        >
          <RefreshCw aria-hidden='true' />
          Retry
        </button>
      )}
    </div>
  );
}

function SourceChoice({
  selected,
  icon: Icon,
  label,
  testId,
  onClick,
  disabled,
}: {
  selected: boolean;
  icon: LucideIcon;
  label: string;
  testId: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type='button'
      className={`flex min-h-[52px] min-w-0 cursor-pointer items-center justify-between gap-[10px] rounded-xl border px-[15px] py-3 text-left text-sm font-semibold transition-colors disabled:cursor-default ${FOCUS_RING_CLASS} max-[480px]:min-h-10 max-[480px]:px-3 max-[480px]:py-2 max-[480px]:text-[13px] ${
        selected
          ? 'border-[#4b7df0] bg-[#eef4ff] text-[#1749bb]'
          : 'border-[#d6dfeb] bg-white text-[#42516a] hover:border-[#9fb8e7] hover:bg-[#f8fbff]'
      }`}
      onClick={onClick}
      aria-pressed={selected}
      disabled={disabled}
      data-testid={testId}
    >
      <span className='inline-flex min-w-0 items-center gap-[9px] max-[480px]:gap-2 [&_svg]:h-[18px] [&_svg]:w-[18px] [&_svg]:shrink-0 max-[480px]:[&_svg]:h-4 max-[480px]:[&_svg]:w-4'>
        <Icon aria-hidden='true' />
        {label}
      </span>
      {selected && (
        <Check className='h-[17px] w-[17px] shrink-0' aria-hidden='true' />
      )}
    </button>
  );
}

export function WxPostSetupStage({
  linked,
  onLinkedChange,
  meetings,
  meetingsPending,
  meetingsError,
  selectedMeeting,
  meetingsLoadingMore,
  hasMoreMeetings,
  onMeetingChange,
  onLoadMoreMeetings,
  onRetryMeetings,
  onCreate,
  isCreating,
  createError,
  sourceLocked,
  articleType,
  onArticleTypeChange,
  customArticleType,
  onCustomArticleTypeChange,
}: {
  linked: boolean;
  onLinkedChange: (linked: boolean) => void;
  meetings: LinkedMeetingOption[];
  meetingsPending: boolean;
  meetingsError: boolean;
  selectedMeeting: LinkedMeetingOption | null;
  meetingsLoadingMore: boolean;
  hasMoreMeetings: boolean;
  onMeetingChange: (meetingId: string) => void;
  onLoadMoreMeetings: () => void;
  onRetryMeetings: () => void;
  onCreate: () => void;
  isCreating: boolean;
  createError: string | null;
  sourceLocked: boolean;
  articleType: WorkspaceArticleType;
  onArticleTypeChange: (value: WorkspaceArticleType) => void;
  customArticleType: string;
  onCustomArticleTypeChange: (value: string) => void;
}) {
  return (
    <div
      className='grid min-w-0 gap-5 max-[480px]:gap-3'
      data-testid='setup-stage'
    >
      <section
        className={`${PANEL_CLASS} overflow-visible ${
          sourceLocked ? 'bg-slate-50' : ''
        }`}
      >
        <div className={PANEL_HEADER_CLASS}>
          <h2 className={PANEL_TITLE_CLASS}>Source</h2>
        </div>

        <div
          className={`grid min-w-0 gap-4 p-[22px] max-[480px]:gap-3 max-[480px]:p-3 ${
            sourceLocked ? 'opacity-70' : ''
          }`}
        >
          <div className='grid min-w-0 grid-cols-2 gap-[10px] max-[760px]:grid-cols-1'>
            <SourceChoice
              selected={linked}
              icon={Link2}
              label='Meeting or event'
              testId='association-linked'
              onClick={() => onLinkedChange(true)}
              disabled={sourceLocked}
            />
            <SourceChoice
              selected={!linked}
              icon={Unlink}
              label='Independent article'
              testId='association-independent'
              onClick={() => onLinkedChange(false)}
              disabled={sourceLocked}
            />
          </div>

          {linked && (
            <MeetingSelect
              meetings={meetings}
              selectedMeeting={selectedMeeting}
              isPending={meetingsPending}
              hasError={meetingsError}
              isLoadingMore={meetingsLoadingMore}
              hasMore={hasMoreMeetings}
              onChange={onMeetingChange}
              onLoadMore={onLoadMoreMeetings}
              onRetry={onRetryMeetings}
              disabled={sourceLocked}
            />
          )}
          {sourceLocked && (
            <p
              className='m-0 text-sm font-medium text-slate-600'
              data-testid='source-locked-message'
            >
              Source is fixed after the workspace is created.
            </p>
          )}
        </div>
      </section>

      <ArticleTypePanel
        value={articleType}
        onChange={onArticleTypeChange}
        customArticleType={customArticleType}
        onCustomArticleTypeChange={onCustomArticleTypeChange}
        disabled={sourceLocked}
      />

      {createError && (
        <p
          className='m-0 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'
          role='alert'
          data-testid='workspace-bootstrap-error'
        >
          {createError}
        </p>
      )}

      {!sourceLocked && (
        <div className='flex items-center justify-end gap-[10px] pt-0.5 max-[760px]:[&_button]:flex-1 max-[480px]:flex-col-reverse max-[480px]:[&_button]:w-full'>
          <button
            type='button'
            className={PRIMARY_BUTTON_CLASS}
            disabled={isCreating || (linked && !selectedMeeting)}
            onClick={onCreate}
            data-testid='create-workspace'
          >
            {isCreating && (
              <Loader2 className='animate-spin' aria-hidden='true' />
            )}
            Create workspace
            {!isCreating && <ArrowRight aria-hidden='true' />}
          </button>
        </div>
      )}
    </div>
  );
}
