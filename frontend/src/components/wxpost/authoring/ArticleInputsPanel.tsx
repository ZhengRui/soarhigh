'use client';

import { useState } from 'react';

import type { WxPostWritingApproach } from '@/components/wxpost/authoring/types';

const WRITING_APPROACHES: WxPostWritingApproach[] = [
  'Chronological',
  'Theme-driven',
  'Image-driven',
  'Highlights first',
];

const PANEL_CLASS =
  'overflow-hidden rounded-2xl border border-[#d9e1ec] bg-white shadow-sm max-[480px]:rounded-[14px]';
const PANEL_HEADER_CLASS =
  'flex min-h-[66px] items-center justify-between gap-[18px] border-b border-[#e4e9f1] px-[22px] py-[18px] max-[480px]:min-h-[60px] max-[480px]:p-4';
const PANEL_TITLE_CLASS =
  'm-0 text-[19px] font-bold leading-[1.35] tracking-[-0.012em] text-[#172033] max-[480px]:text-lg';
const FIELD_CLASS =
  'grid gap-2 text-sm font-bold text-slate-700 [&_textarea]:block [&_textarea]:min-h-[132px] [&_textarea]:w-full [&_textarea]:resize-y [&_textarea]:rounded-[10px] [&_textarea]:border [&_textarea]:border-[#cad5e4] [&_textarea]:bg-white [&_textarea]:px-[13px] [&_textarea]:py-3 [&_textarea]:text-[15px] [&_textarea]:font-normal [&_textarea]:leading-[1.55] [&_textarea]:text-[#172033] [&_textarea]:outline-none [&_textarea]:placeholder:font-normal [&_textarea]:placeholder:text-[#93a0b2] [&_textarea]:hover:border-[#9fb1c8] [&_textarea]:focus:border-blue-600';

export function ArticleInputsPanel() {
  const [writingApproach, setWritingApproach] =
    useState<WxPostWritingApproach>('Chronological');
  const [transcript, setTranscript] = useState('');
  const [notes, setNotes] = useState('');
  const [guidance, setGuidance] = useState('');

  return (
    <>
      <section className={PANEL_CLASS}>
        <div className={PANEL_HEADER_CLASS}>
          <h2 className={PANEL_TITLE_CLASS}>Transcript and notes</h2>
        </div>
        <div className='grid gap-[18px] p-[22px] max-[480px]:p-4'>
          <label className={FIELD_CLASS}>
            <span>Meeting transcript</span>
            <textarea
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              placeholder='Paste a transcript or meeting summary'
              data-testid='meeting-transcript'
            />
          </label>
          <label className={FIELD_CLASS}>
            <span>Extra notes</span>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder='Add facts, emphasis, or details to avoid'
              data-testid='extra-notes'
            />
          </label>
        </div>
      </section>

      <section className={PANEL_CLASS}>
        <div className={PANEL_HEADER_CLASS}>
          <h2 className={PANEL_TITLE_CLASS}>Writing brief</h2>
        </div>
        <div className='p-[22px] max-[480px]:p-4'>
          <fieldset className='mb-5 min-w-0 border-0 p-0'>
            <legend className='mb-[9px] text-sm font-bold text-slate-700'>
              Writing approach
            </legend>
            <div className='flex flex-wrap gap-2'>
              {WRITING_APPROACHES.map((approach) => {
                const selected = writingApproach === approach;
                return (
                  <button
                    key={approach}
                    type='button'
                    className={`min-h-10 cursor-pointer rounded-full border px-[14px] py-[9px] text-sm font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 ${
                      selected
                        ? 'border-[#4b7df0] bg-[#eaf2ff] text-[#1749bb]'
                        : 'border-[#d3dce8] bg-white text-[#516079] hover:border-[#9fb8e7] hover:bg-[#f8fbff]'
                    }`}
                    aria-pressed={selected}
                    onClick={() => setWritingApproach(approach)}
                    data-testid={`writing-approach-${approach.toLowerCase().replaceAll(' ', '-')}`}
                  >
                    {approach}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <label className={FIELD_CLASS}>
            <span>Writing guidance</span>
            <textarea
              value={guidance}
              onChange={(event) => setGuidance(event.target.value)}
              placeholder='Describe the desired angle, tone, and emphasis'
              data-testid='writing-guidance'
            />
          </label>
        </div>
      </section>
    </>
  );
}
