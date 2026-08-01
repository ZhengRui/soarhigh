'use client';

import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

import type { MeetingIF } from '@/interfaces';

import { formatMeetingType } from './meetingLabels';

function truncateText(text: string, limit: number) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > limit
    ? `${normalized.slice(0, limit).trim()}…`
    : normalized;
}

function DetailToggle({
  title,
  summary,
  open,
  onToggle,
  children,
  testId,
}: {
  title: string;
  summary: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <section className='overflow-hidden rounded-xl border border-[#d8e1ed] bg-[#f7f9fc]'>
      <button
        type='button'
        className='grid min-h-14 w-full grid-cols-[115px_minmax(0,1fr)_20px] items-center gap-[14px] border-0 bg-transparent px-[15px] py-[13px] text-left text-[#41516b] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 max-[760px]:grid-cols-[94px_minmax(0,1fr)_18px] max-[480px]:grid-cols-[82px_minmax(0,1fr)_18px] max-[480px]:gap-[9px] max-[480px]:p-3'
        aria-expanded={open}
        onClick={onToggle}
        data-testid={`${testId}-toggle`}
      >
        <strong className='text-sm'>{title}</strong>
        <span className='overflow-hidden text-ellipsis whitespace-nowrap text-sm leading-[1.45]'>
          {open ? '' : summary}
        </span>
        <ChevronDown
          aria-hidden='true'
          className={`h-[17px] w-[17px] transition-transform duration-150 ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>
      {open && (
        <div
          className='px-[15px] pb-4 text-[15px] leading-7 text-[#42516a] max-[480px]:px-3 max-[480px]:pb-[13px]'
          data-testid={testId}
        >
          {children}
        </div>
      )}
    </section>
  );
}

const TABLE_CLASS =
  'w-full border-collapse text-sm leading-[1.45] text-[#27364d] [&_td]:border-b [&_td]:border-[#e4e9f1] [&_td]:px-[14px] [&_td]:py-3 [&_td]:text-left [&_td]:align-top [&_th]:sticky [&_th]:top-0 [&_th]:z-[1] [&_th]:border-b [&_th]:border-[#e4e9f1] [&_th]:bg-[#f5f7fa] [&_th]:px-[14px] [&_th]:py-3 [&_th]:text-left [&_th]:align-top [&_th]:text-xs [&_th]:font-bold [&_th]:uppercase [&_th]:tracking-[0.045em] [&_th]:text-[#66758b] [&_tr:last-child_td]:border-b-0';

export function MeetingContextPanel({ meeting }: { meeting: MeetingIF }) {
  const [open, setOpen] = useState(false);
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [agendaOpen, setAgendaOpen] = useState(false);
  const [awardsOpen, setAwardsOpen] = useState(false);

  const agendaSummary = meeting.segments
    .map((segment) => segment.type)
    .join(' · ');
  const awards = meeting.awards ?? [];
  const awardsSummary = awards
    .map((award) => `${award.category}: ${award.winner}`)
    .join(' · ');

  return (
    <section
      className='overflow-hidden rounded-2xl border border-[#d9e1ec] bg-white shadow-sm max-[480px]:rounded-[14px]'
      data-testid='meeting-context'
    >
      <button
        type='button'
        className='flex min-h-[72px] w-full items-center justify-between gap-5 border-0 bg-white px-[22px] py-[17px] text-left text-[#172033] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 max-[480px]:min-h-[60px] max-[480px]:gap-3 max-[480px]:px-3 max-[480px]:py-3'
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        data-testid='meeting-context-toggle'
      >
        <span className='grid min-w-0 gap-[5px]'>
          <strong className='text-[19px] leading-[1.3] max-[480px]:text-base'>
            Meeting context
          </strong>
          <small className='overflow-hidden text-ellipsis whitespace-nowrap text-sm leading-[1.45] text-slate-500 max-[480px]:text-[13px]'>
            {formatMeetingType(meeting)}
            {meeting.no ? ` · #${meeting.no}` : ''} · {meeting.date} ·{' '}
            {meeting.theme}
          </small>
        </span>
        <span className='inline-flex items-center gap-[6px] text-[13px] font-semibold text-[#52627a] max-[480px]:text-[0]'>
          {open ? 'Hide' : 'Show'}
          <ChevronDown
            aria-hidden='true'
            className={`h-[17px] w-[17px] transition-transform duration-150 ${
              open ? 'rotate-180' : ''
            }`}
          />
        </span>
      </button>

      {open && (
        <div className='grid gap-3 border-t border-[#e4e9f1] px-[22px] pb-[22px] max-[480px]:px-3 max-[480px]:pb-3'>
          <div className='mt-[22px] grid grid-cols-[0.7fr_1fr_1.5fr_1.4fr] overflow-hidden rounded-xl border border-[#d8e1ed] bg-[#f7f9fc] max-[760px]:grid-cols-2 max-[480px]:mt-3 max-[480px]:grid-cols-1'>
            {[
              ['Meeting', meeting.no ? `#${meeting.no}` : meeting.type],
              ['Date', meeting.date],
              ['Venue', meeting.location],
              ['Theme', meeting.theme],
            ].map(([label, value], index) => (
              <div
                key={label}
                className={`grid min-w-0 gap-[6px] border-[#dfe6ef] px-4 py-[14px] max-[480px]:gap-1 max-[480px]:border-b max-[480px]:border-r-0 max-[480px]:px-3 max-[480px]:py-2.5 max-[480px]:last:border-b-0 ${
                  index < 3 ? 'border-r' : ''
                } ${
                  index < 2 ? 'max-[760px]:border-b' : 'max-[760px]:border-b-0'
                } ${index === 1 ? 'max-[760px]:border-r-0' : ''}`}
              >
                <span className='text-xs font-bold uppercase tracking-[0.06em] text-[#718096]'>
                  {label}
                </span>
                <strong className='break-words text-sm leading-[1.4] text-[#172033] [overflow-wrap:anywhere]'>
                  {value}
                </strong>
              </div>
            ))}
          </div>

          <DetailToggle
            title='Description'
            summary={truncateText(meeting.introduction, 180)}
            open={descriptionOpen}
            onToggle={() => setDescriptionOpen((value) => !value)}
            testId='meeting-description'
          >
            <p className='m-0 whitespace-pre-line'>{meeting.introduction}</p>
          </DetailToggle>

          <DetailToggle
            title='Agenda'
            summary={truncateText(agendaSummary, 180)}
            open={agendaOpen}
            onToggle={() => setAgendaOpen((value) => !value)}
            testId='meeting-agenda'
          >
            <div className='max-h-[440px] overflow-auto rounded-[10px] border border-[#dce3ec] bg-white'>
              <table className={TABLE_CLASS}>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Segment / role</th>
                    <th>Role taker</th>
                    <th>Speech / workshop title</th>
                  </tr>
                </thead>
                <tbody>
                  {meeting.segments.map((segment) => (
                    <tr key={segment.id}>
                      <td>{segment.start_time}</td>
                      <td>{segment.type}</td>
                      <td>{segment.role_taker?.name || '—'}</td>
                      <td>{segment.title || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DetailToggle>

          {awards.length > 0 && (
            <DetailToggle
              title='Award winners'
              summary={truncateText(awardsSummary, 180)}
              open={awardsOpen}
              onToggle={() => setAwardsOpen((value) => !value)}
              testId='meeting-awards'
            >
              <div className='max-h-[440px] overflow-auto rounded-[10px] border border-[#dce3ec] bg-white'>
                <table className={TABLE_CLASS}>
                  <thead>
                    <tr>
                      <th>Award</th>
                      <th>Winner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {awards.map((award) => (
                      <tr key={`${award.category}-${award.winner}`}>
                        <td>{award.category}</td>
                        <td>{award.winner}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DetailToggle>
          )}
        </div>
      )}
    </section>
  );
}
