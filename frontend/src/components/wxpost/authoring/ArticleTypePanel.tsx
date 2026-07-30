'use client';

import {
  CalendarCheck2,
  Check,
  ClipboardCheck,
  ListChecks,
  Megaphone,
  Shapes,
  UserRound,
  type LucideIcon,
} from 'lucide-react';

import {
  WORKSPACE_ARTICLE_TYPE_LABELS,
  type WorkspaceArticleType,
} from '@/utils/wxpostWorkspace';

import {
  FOCUS_RING_CLASS,
  PANEL_CLASS,
  PANEL_HEADER_CLASS,
  PANEL_TITLE_CLASS,
} from './authoringStyles';

const ARTICLE_TYPES = [
  { value: 'meeting-recap', icon: CalendarCheck2 },
  { value: 'member-story', icon: UserRound },
  { value: 'event-preview', icon: Megaphone },
  { value: 'meeting-review', icon: ClipboardCheck },
  { value: 'action-guide', icon: ListChecks },
  { value: 'custom', icon: Shapes },
] satisfies Array<{
  value: WorkspaceArticleType;
  icon: LucideIcon;
}>;

export function ArticleTypePanel({
  value,
  onChange,
  customArticleType,
  onCustomArticleTypeChange,
}: {
  value: WorkspaceArticleType;
  onChange: (type: WorkspaceArticleType) => void;
  customArticleType: string;
  onCustomArticleTypeChange: (value: string) => void;
}) {
  return (
    <section className={PANEL_CLASS} data-testid='article-type-panel'>
      <div className={PANEL_HEADER_CLASS}>
        <h2 className={PANEL_TITLE_CLASS}>Article type</h2>
      </div>
      <div className='grid gap-4 p-[22px] max-[480px]:gap-3 max-[480px]:p-3'>
        <div className='grid grid-cols-3 gap-[10px] max-[760px]:grid-cols-2 max-[480px]:grid-cols-1'>
          {ARTICLE_TYPES.map(({ value: type, icon: Icon }) => {
            const selected = value === type;
            const label = WORKSPACE_ARTICLE_TYPE_LABELS[type];
            return (
              <button
                type='button'
                key={type}
                className={`flex min-h-[52px] min-w-0 cursor-pointer items-center justify-between gap-[10px] rounded-xl border px-[15px] py-3 text-left text-sm font-semibold transition-colors ${FOCUS_RING_CLASS} max-[480px]:min-h-10 max-[480px]:px-3 max-[480px]:py-2 max-[480px]:text-[13px] ${
                  selected
                    ? 'border-[#4b7df0] bg-[#eef4ff] text-[#1749bb]'
                    : 'border-[#d6dfeb] bg-white text-[#40506a] hover:border-[#9fb8e7] hover:bg-[#f8fbff]'
                }`}
                onClick={() => onChange(type)}
                aria-pressed={selected}
                data-testid={`article-type-${type}`}
              >
                <span className='inline-flex min-w-0 items-center gap-[9px] max-[480px]:gap-2 [&_svg]:h-[18px] [&_svg]:w-[18px] [&_svg]:shrink-0 max-[480px]:[&_svg]:h-4 max-[480px]:[&_svg]:w-4'>
                  <Icon aria-hidden='true' />
                  {label}
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
        {value === 'custom' && (
          <label className='grid gap-2 border-t border-slate-200 pt-4 max-[480px]:pt-3'>
            <span className='text-sm font-bold text-slate-700'>
              Custom article type (optional)
            </span>
            <input
              type='text'
              value={customArticleType}
              onChange={(event) =>
                onCustomArticleTypeChange(event.target.value)
              }
              placeholder='For example: Member interview'
              className='min-h-[46px] rounded-[10px] border border-[#cad5e4] bg-white px-3 text-[15px] text-[#172033] outline-none placeholder:text-[#93a0b2] hover:border-[#9fb1c8] focus:border-blue-600 max-[480px]:min-h-10 max-[480px]:text-sm'
              data-testid='custom-article-type'
            />
          </label>
        )}
      </div>
    </section>
  );
}
