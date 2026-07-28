'use client';

import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  ArrowRight,
  CalendarCheck2,
  Check,
  ChevronDown,
  ChevronLeft,
  ClipboardCheck,
  Link2,
  ListChecks,
  Loader2,
  Megaphone,
  RefreshCw,
  Shapes,
  Unlink,
  UserRound,
  type LucideIcon,
} from 'lucide-react';
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

import { ArticleInputsPanel } from '@/components/wxpost/authoring/ArticleInputsPanel';
import { MaterialsPanel } from '@/components/wxpost/authoring/MaterialsPanel';
import { MeetingContextPanel } from '@/components/wxpost/authoring/MeetingContextPanel';
import type {
  WxPostArticleType,
  WxPostAuthoringStage,
  WxPostMaterial,
} from '@/components/wxpost/authoring/types';
import { useMeeting } from '@/hooks/useMeeting';
import { useMeetingOptions } from '@/hooks/useMeetingOptions';
import type { MeetingIF, MeetingOptionIF } from '@/interfaces';
import { listMeetingMedia, type MediaFileList } from '@/utils/alicloud';

type LinkedMeeting = MeetingIF & { id: string };
type LinkedMeetingOption = MeetingOptionIF;

const ARTICLE_TYPES = [
  { value: 'Meeting Recap', icon: CalendarCheck2 },
  { value: 'Member Story', icon: UserRound },
  { value: 'Event Preview', icon: Megaphone },
  { value: 'Meeting Review', icon: ClipboardCheck },
  { value: 'Action Guide', icon: ListChecks },
  { value: 'Custom', icon: Shapes },
] satisfies Array<{
  value: WxPostArticleType;
  icon: LucideIcon;
}>;

const PANEL_CLASS =
  'overflow-hidden rounded-2xl border border-[#d9e1ec] bg-white shadow-sm max-[480px]:rounded-[14px]';
const PANEL_HEADER_CLASS =
  'flex min-h-[66px] items-center justify-between gap-[18px] border-b border-[#e4e9f1] px-[22px] py-[18px] max-[480px]:min-h-[60px] max-[480px]:p-4';
const PANEL_TITLE_CLASS =
  'm-0 text-[19px] font-bold leading-[1.35] tracking-[-0.012em] text-[#172033] max-[480px]:text-lg';
const FOCUS_RING_CLASS =
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600';
const PRIMARY_BUTTON_CLASS = `inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-[#245feb] bg-[#245feb] px-4 py-[10px] text-sm font-bold text-white hover:border-[#184bc7] hover:bg-[#184bc7] ${FOCUS_RING_CLASS} disabled:cursor-not-allowed disabled:border-[#dce3ec] disabled:bg-[#eef2f6] disabled:text-[#96a2b2] [&_svg]:h-[17px] [&_svg]:w-[17px]`;
const SECONDARY_BUTTON_CLASS = `inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-[#cfd9e6] bg-white px-4 py-[10px] text-sm font-bold text-[#40506a] hover:border-[#9fb1c8] hover:bg-slate-50 ${FOCUS_RING_CLASS} disabled:cursor-not-allowed disabled:border-[#dce3ec] disabled:bg-[#eef2f6] disabled:text-[#96a2b2] [&_svg]:h-[17px] [&_svg]:w-[17px]`;
const STAGE_BUTTON_CLASS = `relative flex min-h-[60px] items-center justify-center gap-[9px] border-r border-[#e4e9f1] bg-transparent text-sm font-semibold text-[#68758a] last:border-r-0 ${FOCUS_RING_CLASS} max-[760px]:min-h-[54px] max-[760px]:gap-[5px] max-[760px]:text-xs max-[480px]:min-w-0 max-[480px]:flex-col max-[480px]:gap-[3px] max-[480px]:px-0.5 max-[480px]:py-[7px] max-[480px]:leading-[1.15] [&>span]:grid [&>span]:h-[25px] [&>span]:w-[25px] [&>span]:place-items-center [&>span]:rounded-full [&>span]:bg-[#eef2f7] [&>span]:text-xs max-[760px]:[&>span]:h-[21px] max-[760px]:[&>span]:w-[21px] [&>span>svg]:h-[14px] [&>span>svg]:w-[14px]`;

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
    meeting.type,
    formatDate(meeting.date),
    meeting.theme,
  ]
    .filter(Boolean)
    .join(' · ');
}

function isVideoFile(filename: string) {
  return /\.(mp4|mov|m4v|webm|avi|mkv)$/i.test(filename);
}

function ArticleTypePicker({
  value,
  onChange,
}: {
  value: WxPostArticleType;
  onChange: (type: WxPostArticleType) => void;
}) {
  return (
    <section className={PANEL_CLASS} data-testid='article-type-panel'>
      <div className={PANEL_HEADER_CLASS}>
        <h2 className={PANEL_TITLE_CLASS}>Article type</h2>
      </div>
      <div className='grid grid-cols-3 gap-[10px] p-[22px] max-[760px]:grid-cols-2 max-[480px]:grid-cols-1 max-[480px]:p-4'>
        {ARTICLE_TYPES.map(({ value: type, icon: Icon }) => {
          const selected = value === type;
          return (
            <button
              type='button'
              key={type}
              className={`flex min-h-[52px] cursor-pointer items-center justify-between gap-[10px] rounded-xl border px-[15px] py-3 text-left text-sm font-semibold transition-colors ${FOCUS_RING_CLASS} ${
                selected
                  ? 'border-[#4b7df0] bg-[#eef4ff] text-[#1749bb]'
                  : 'border-[#d6dfeb] bg-white text-[#40506a] hover:border-[#9fb8e7] hover:bg-[#f8fbff]'
              }`}
              onClick={() => onChange(type)}
              aria-pressed={selected}
              data-testid={`article-type-${type.toLowerCase().replaceAll(' ', '-')}`}
            >
              <span className='inline-flex min-w-0 items-center gap-[9px] [&_svg]:h-[18px] [&_svg]:w-[18px] [&_svg]:shrink-0'>
                <Icon aria-hidden='true' />
                {type}
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
    </section>
  );
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
    <div className='grid gap-2'>
      <span className='text-sm font-bold text-slate-700'>Meeting or event</span>
      <div className='relative' ref={containerRef}>
        <button
          type='button'
          className='relative flex min-h-[50px] w-full cursor-pointer items-center rounded-[11px] border border-[#cad5e4] bg-white py-0 pl-[15px] pr-12 text-left text-[15px] text-[#172033] outline-none hover:border-[#9fb1c8] focus-visible:border-blue-600 focus-visible:outline-none aria-expanded:border-blue-600 disabled:cursor-default disabled:bg-[#f7f9fc] disabled:text-[#8290a4]'
          aria-haspopup='listbox'
          aria-expanded={open}
          aria-controls='wxpost-meeting-options'
          disabled={isPending || hasError || meetings.length === 0}
          onClick={() => setOpen((value) => !value)}
          data-testid='meeting-select-trigger'
        >
          <span className='overflow-hidden text-ellipsis whitespace-nowrap'>
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
              className={`pointer-events-none absolute right-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-500 transition-transform duration-150 ${
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
              className='max-h-[294px] overflow-y-auto p-[6px]'
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
                    className={`flex min-h-10 w-full cursor-pointer items-center justify-between gap-[14px] rounded-[7px] border-0 px-[11px] py-[9px] text-left text-sm leading-[1.4] ${
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

function StageTabs({
  stage,
  canOpenMaterials,
  onStageChange,
}: {
  stage: WxPostAuthoringStage;
  canOpenMaterials: boolean;
  onStageChange: (stage: WxPostAuthoringStage) => void;
}) {
  const activeClass =
    'bg-[#eff5ff] text-blue-700 after:absolute after:bottom-0 after:left-[18px] after:right-[18px] after:h-0.5 after:rounded-t-full after:bg-blue-600 [&>span]:bg-blue-600 [&>span]:text-white';

  return (
    <nav
      className='mb-6 grid grid-cols-4 overflow-hidden rounded-[14px] border border-[#d9e1ec] bg-white max-[480px]:rounded-xl'
      aria-label='WXPost creation progress'
    >
      <button
        type='button'
        className={`${STAGE_BUTTON_CLASS} ${
          stage === 'setup'
            ? activeClass
            : 'text-[#245feb] [&>span]:bg-[#e7efff] [&>span]:text-[#245feb]'
        }`}
        onClick={() => onStageChange('setup')}
      >
        <span>{stage === 'materials' ? <Check /> : '1'}</span>
        Setup
      </button>
      <button
        type='button'
        className={`${STAGE_BUTTON_CLASS} ${
          stage === 'materials' ? activeClass : ''
        }`}
        onClick={() => onStageChange('materials')}
        disabled={!canOpenMaterials}
      >
        <span>2</span>
        Materials
      </button>
      <button
        type='button'
        className={`${STAGE_BUTTON_CLASS} cursor-default text-[#a2adbd]`}
        disabled
      >
        <span>3</span>
        Draft
      </button>
      <button
        type='button'
        className={`${STAGE_BUTTON_CLASS} cursor-default text-[#a2adbd]`}
        disabled
      >
        <span>4</span>
        Preview
      </button>
    </nav>
  );
}

function SourceChoice({
  selected,
  icon: Icon,
  label,
  testId,
  onClick,
}: {
  selected: boolean;
  icon: LucideIcon;
  label: string;
  testId: string;
  onClick: () => void;
}) {
  return (
    <button
      type='button'
      className={`group grid min-h-[74px] cursor-pointer grid-cols-[40px_minmax(0,1fr)_20px] items-center gap-[13px] rounded-[13px] border px-4 py-[14px] text-left transition-colors ${FOCUS_RING_CLASS} max-[480px]:min-h-[66px] ${
        selected
          ? 'border-[#4b7df0] bg-[#eef4ff] text-[#1749bb]'
          : 'border-[#d6dfeb] bg-white text-[#42516a] hover:border-[#9fb8e7] hover:bg-[#f8fbff]'
      }`}
      onClick={onClick}
      aria-pressed={selected}
      data-testid={testId}
    >
      <span
        className={`grid h-10 w-10 place-items-center rounded-[10px] [&_svg]:h-[18px] [&_svg]:w-[18px] ${
          selected
            ? 'bg-[#dce8ff] text-[#245feb]'
            : 'bg-[#f0f4fa] text-[#5c6b82]'
        }`}
      >
        <Icon aria-hidden='true' />
      </span>
      <strong className='min-w-0 text-[15px] font-bold'>{label}</strong>
      {selected && <Check className='h-[18px] w-[18px]' aria-hidden='true' />}
    </button>
  );
}

function SetupStage({
  articleType,
  onArticleTypeChange,
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
  onContinue,
}: {
  articleType: WxPostArticleType;
  onArticleTypeChange: (type: WxPostArticleType) => void;
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
  onContinue: () => void;
}) {
  return (
    <div className='grid gap-5' data-testid='setup-stage'>
      <ArticleTypePicker value={articleType} onChange={onArticleTypeChange} />

      <section className={`${PANEL_CLASS} overflow-visible`}>
        <div className={PANEL_HEADER_CLASS}>
          <h2 className={PANEL_TITLE_CLASS}>Source</h2>
        </div>

        <div className='grid gap-[22px] p-[22px] max-[480px]:p-4'>
          <div className='grid grid-cols-2 gap-3 max-[760px]:grid-cols-1'>
            <SourceChoice
              selected={linked}
              icon={Link2}
              label='Meeting or event'
              testId='association-linked'
              onClick={() => onLinkedChange(true)}
            />
            <SourceChoice
              selected={!linked}
              icon={Unlink}
              label='Independent article'
              testId='association-independent'
              onClick={() => onLinkedChange(false)}
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
            />
          )}
        </div>
      </section>

      <div className='flex items-center justify-end gap-[10px] pt-0.5 max-[760px]:[&_button]:flex-1 max-[480px]:flex-col-reverse max-[480px]:[&_button]:w-full'>
        <button
          type='button'
          className={PRIMARY_BUTTON_CLASS}
          disabled={linked && !selectedMeeting}
          onClick={onContinue}
          data-testid='continue-to-materials'
        >
          Continue to materials
          <ArrowRight aria-hidden='true' />
        </button>
      </div>
    </div>
  );
}

function MaterialsStage({
  active,
  articleType,
  onArticleTypeChange,
  meetingId,
  onBack,
}: {
  active: boolean;
  articleType: WxPostArticleType;
  onArticleTypeChange: (type: WxPostArticleType) => void;
  meetingId: string | null;
  onBack: () => void;
}) {
  const meetingQuery = useMeeting(active && meetingId ? meetingId : undefined);
  const meeting =
    meetingQuery.data?.id === meetingId
      ? (meetingQuery.data as LinkedMeeting)
      : null;
  const meetingPending = Boolean(meetingId) && meetingQuery.isPending;
  const mediaQuery = useQuery<MediaFileList>({
    queryKey: ['meeting-media', meeting?.id],
    queryFn: () =>
      listMeetingMedia(meeting?.id as string) as Promise<MediaFileList>,
    enabled: active && Boolean(meeting?.id),
    staleTime: 60 * 1000,
  });

  const materials = useMemo<WxPostMaterial[]>(
    () =>
      (mediaQuery.data?.items ?? []).map((file) => ({
        id: file.fileKey,
        source: 'Meeting Library',
        kind: isVideoFile(file.filename) ? 'video' : 'image',
        url: file.url,
        filename: file.filename,
        description: '',
        workspaceReady: false,
        included: false,
      })),
    [mediaQuery.data?.items]
  );
  const loadError = meetingQuery.isError
    ? {
        message: 'Unable to load meeting details',
        retry: () => {
          void meetingQuery.refetch();
        },
      }
    : mediaQuery.isError
      ? {
          message: 'Unable to load meeting media',
          retry: () => {
            void mediaQuery.refetch();
          },
        }
      : null;

  return (
    <div className='grid gap-5' data-testid='materials-stage'>
      <ArticleTypePicker value={articleType} onChange={onArticleTypeChange} />
      {meeting && <MeetingContextPanel meeting={meeting} />}
      <MaterialsPanel
        materials={materials}
        isLoading={meetingPending || (Boolean(meeting) && mediaQuery.isPending)}
        errorMessage={loadError?.message ?? null}
        onRetry={loadError?.retry}
        collectionKey={meeting?.id ?? 'independent'}
      />
      <ArticleInputsPanel />

      <div className='flex items-center justify-end gap-[10px] pt-0.5 max-[760px]:[&_button]:flex-1 max-[480px]:flex-col-reverse max-[480px]:[&_button]:w-full'>
        <button
          type='button'
          className={SECONDARY_BUTTON_CLASS}
          onClick={onBack}
        >
          <ChevronLeft aria-hidden='true' />
          Change setup
        </button>
        <button type='button' className={PRIMARY_BUTTON_CLASS} disabled>
          Generate English draft
          <ArrowRight aria-hidden='true' />
        </button>
      </div>
    </div>
  );
}

export function WxPostAuthoringWorkspace() {
  const [stage, setStage] = useState<WxPostAuthoringStage>('setup');
  const [articleType, setArticleType] =
    useState<WxPostArticleType>('Meeting Recap');
  const [linked, setLinked] = useState(true);
  const [selectedMeeting, setSelectedMeeting] =
    useState<LinkedMeetingOption | null>(null);
  const meetingsQuery = useMeetingOptions();

  const meetings = useMemo(
    () =>
      (meetingsQuery.data?.pages.flatMap((page) => page.items) ?? []).filter(
        (meeting): meeting is LinkedMeetingOption => Boolean(meeting.id)
      ),
    [meetingsQuery.data?.pages]
  );

  useEffect(() => {
    if (!selectedMeeting && meetings.length > 0) {
      setSelectedMeeting(meetings[0]);
    }
  }, [meetings, selectedMeeting]);

  const effectiveMeeting = linked ? selectedMeeting : null;
  const canOpenMaterials = !linked || Boolean(selectedMeeting);

  return (
    <div className='min-h-screen bg-[#f3f6fa] text-base text-[#172033]'>
      <div className='mx-auto w-[min(calc(100%_-_40px),1080px)] py-[34px] pb-[72px] max-[760px]:w-[min(calc(100%_-_24px),1080px)] max-[760px]:pt-6 max-[480px]:w-[min(calc(100%_-_20px),1080px)]'>
        <Link
          href='/posts'
          className='mb-6 inline-flex items-center gap-2 text-sm font-semibold text-[#46556f] no-underline hover:text-[#245feb] max-[480px]:mb-[18px] [&_svg]:h-[17px] [&_svg]:w-[17px]'
        >
          <ArrowLeft aria-hidden='true' />
          Back to Posts
        </Link>

        <header className='mb-[26px] max-[480px]:mb-5'>
          <h1 className='m-0 text-[clamp(30px,4vw,40px)] font-bold leading-[1.12] tracking-[-0.035em] text-slate-900 max-[760px]:text-[30px] max-[480px]:text-[28px]'>
            New WeChat Post
          </h1>
          <p className='mb-0 mt-[10px] text-base leading-6 text-slate-500 max-[480px]:text-sm'>
            {effectiveMeeting
              ? `${effectiveMeeting.type}${effectiveMeeting.no ? ` #${effectiveMeeting.no}` : ''} · ${articleType}`
              : `Independent article · ${articleType}`}
          </p>
        </header>

        <StageTabs
          stage={stage}
          canOpenMaterials={canOpenMaterials}
          onStageChange={setStage}
        />

        <div hidden={stage !== 'setup'}>
          <SetupStage
            articleType={articleType}
            onArticleTypeChange={setArticleType}
            linked={linked}
            onLinkedChange={setLinked}
            meetings={meetings}
            meetingsPending={meetingsQuery.isPending}
            meetingsError={meetingsQuery.isError}
            selectedMeeting={selectedMeeting}
            meetingsLoadingMore={meetingsQuery.isFetchingNextPage}
            hasMoreMeetings={meetingsQuery.hasNextPage}
            onMeetingChange={(meetingId) => {
              const meeting =
                meetings.find((item) => item.id === meetingId) ?? null;
              if (meeting) setSelectedMeeting(meeting);
            }}
            onLoadMoreMeetings={() => {
              void meetingsQuery.fetchNextPage();
            }}
            onRetryMeetings={() => {
              void meetingsQuery.refetch();
            }}
            onContinue={() => setStage('materials')}
          />
        </div>

        <div hidden={stage !== 'materials'}>
          <MaterialsStage
            key={effectiveMeeting?.id ?? 'independent'}
            active={stage === 'materials'}
            articleType={articleType}
            onArticleTypeChange={setArticleType}
            meetingId={effectiveMeeting?.id ?? null}
            onBack={() => setStage('setup')}
          />
        </div>
      </div>
    </div>
  );
}
