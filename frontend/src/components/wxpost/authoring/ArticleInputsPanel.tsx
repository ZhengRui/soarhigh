'use client';

import {
  WORKSPACE_WRITING_APPROACH_LABELS,
  type WorkspaceWritingApproach,
} from '@/utils/wxpostWorkspace';

import { ResizableTextarea } from './ResizableTextarea';
import {
  PANEL_CLASS,
  PANEL_HEADER_CLASS,
  PANEL_TITLE_CLASS,
} from './authoringStyles';

const WRITING_APPROACHES: WorkspaceWritingApproach[] = [
  'chronological',
  'theme-driven',
  'image-driven',
  'highlights-first',
];

const FIELD_CLASS =
  'grid gap-2 text-sm font-bold text-slate-700 [&_textarea]:block [&_textarea]:min-h-[132px] [&_textarea]:w-full [&_textarea]:rounded-[10px] [&_textarea]:border [&_textarea]:border-[#cad5e4] [&_textarea]:bg-white [&_textarea]:px-[13px] [&_textarea]:pb-8 [&_textarea]:pt-3 [&_textarea]:text-[15px] [&_textarea]:font-normal [&_textarea]:leading-[1.55] [&_textarea]:text-[#172033] [&_textarea]:outline-none [&_textarea]:placeholder:font-normal [&_textarea]:placeholder:text-[#93a0b2] [&_textarea]:hover:border-[#9fb1c8] [&_textarea]:focus:border-blue-600';

export function ArticleInputsPanel({
  writingApproach,
  transcript,
  extraNotes,
  writingGuidance,
  onWritingApproachChange,
  onTranscriptChange,
  onExtraNotesChange,
  onWritingGuidanceChange,
}: {
  writingApproach: WorkspaceWritingApproach;
  transcript: string;
  extraNotes: string;
  writingGuidance: string;
  onWritingApproachChange: (value: WorkspaceWritingApproach) => void;
  onTranscriptChange: (value: string) => void;
  onExtraNotesChange: (value: string) => void;
  onWritingGuidanceChange: (value: string) => void;
}) {
  return (
    <>
      <section className={PANEL_CLASS}>
        <div className={PANEL_HEADER_CLASS}>
          <h2 className={PANEL_TITLE_CLASS}>Transcript and notes</h2>
        </div>
        <div className='grid gap-[18px] p-[22px] max-[480px]:p-4'>
          <label className={FIELD_CLASS}>
            <span>Meeting transcript</span>
            <ResizableTextarea
              value={transcript}
              onChange={(event) => onTranscriptChange(event.target.value)}
              placeholder='Paste a transcript or meeting summary'
              data-testid='meeting-transcript'
              resizeHandleTestId='meeting-transcript-resize-handle'
            />
          </label>
          <label className={FIELD_CLASS}>
            <span>Extra notes</span>
            <ResizableTextarea
              value={extraNotes}
              onChange={(event) => onExtraNotesChange(event.target.value)}
              placeholder='Add facts, emphasis, or details to avoid'
              data-testid='extra-notes'
              resizeHandleTestId='extra-notes-resize-handle'
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
                    onClick={() => onWritingApproachChange(approach)}
                    data-testid={`writing-approach-${approach.toLowerCase().replaceAll(' ', '-')}`}
                  >
                    {WORKSPACE_WRITING_APPROACH_LABELS[approach]}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <label className={FIELD_CLASS}>
            <span>Writing guidance</span>
            <ResizableTextarea
              value={writingGuidance}
              onChange={(event) => onWritingGuidanceChange(event.target.value)}
              placeholder='Describe the desired angle, tone, and emphasis'
              data-testid='writing-guidance'
              resizeHandleTestId='writing-guidance-resize-handle'
            />
          </label>
        </div>
      </section>
    </>
  );
}
