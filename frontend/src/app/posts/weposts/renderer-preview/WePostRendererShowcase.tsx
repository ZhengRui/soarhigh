'use client';

import { useState } from 'react';

import {
  WEPOST_FIXTURES,
  WEPOST_FIXTURE_CONTEXT_LABELS,
  WEPOST_FIXTURE_IDS,
  type WePostFixtureId,
} from '@/components/wepost/fixtures';
import {
  WePostPresentationControls,
  type WePostPresentationSelection,
} from '@/components/wepost/WePostPresentationControls';
import { WePostRenderer } from '@/components/wepost/WePostRenderer';

const DEFAULT_SELECTION: WePostPresentationSelection = {
  layout: 'brand-default',
  palette: 'paper-neutral',
  appearance: 'light',
  typeface: 'editorial-serif',
  previewSize: 'mobile-390',
};

const FIXTURE_LABELS: Record<WePostFixtureId, string> = {
  'meeting-recap': 'Meeting Recap',
  'member-story': 'Member Story',
  'event-preview': 'Event Preview',
};

export function WePostRendererShowcase() {
  const [fixtureId, setFixtureId] = useState<WePostFixtureId>('meeting-recap');
  const [selection, setSelection] =
    useState<WePostPresentationSelection>(DEFAULT_SELECTION);

  const article = WEPOST_FIXTURES[fixtureId];

  return (
    <div className='min-h-screen bg-slate-100 px-4 py-10 sm:px-6'>
      <div className='mx-auto max-w-6xl'>
        <header className='mb-8 grid gap-3'>
          <span className='text-xs font-semibold uppercase tracking-[0.18em] text-blue-700'>
            WePost Renderer Lab
          </span>
          <h1 className='text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl'>
            One article, every presentation choice
          </h1>
          <p className='max-w-3xl text-slate-600'>
            Three backend-generated article shapes exercise the complete
            WePostRenderDocument v1 renderer. Controls change only this local
            preview.
          </p>
        </header>

        <section
          className='mb-4 flex flex-wrap items-center gap-2'
          aria-label='Article fixtures'
        >
          <span className='mr-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500'>
            Fixture
          </span>
          {WEPOST_FIXTURE_IDS.map((id) => (
            <button
              key={id}
              className={`rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                fixtureId === id
                  ? 'border-blue-600 bg-blue-600 text-white shadow-sm'
                  : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900'
              }`}
              type='button'
              aria-pressed={fixtureId === id}
              data-testid={`fixture-option-${id}`}
              onClick={() => setFixtureId(id)}
            >
              {FIXTURE_LABELS[id]}
            </button>
          ))}
        </section>

        <WePostPresentationControls
          value={selection}
          onChange={setSelection}
          onReset={() => setSelection(DEFAULT_SELECTION)}
        />

        <WePostRenderer
          article={article}
          presentation={{
            layout: selection.layout,
            palette: selection.palette,
            appearance: selection.appearance,
            typeface: selection.typeface,
          }}
          previewSize={selection.previewSize}
          contextLabel={WEPOST_FIXTURE_CONTEXT_LABELS[fixtureId]}
        />
      </div>
    </div>
  );
}
