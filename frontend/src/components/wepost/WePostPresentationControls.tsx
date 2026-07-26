'use client';

import { RotateCcw } from 'lucide-react';

import {
  WEPOST_APPEARANCES,
  WEPOST_LAYOUTS,
  WEPOST_PALETTES,
  WEPOST_PREVIEW_SIZES,
  WEPOST_TYPEFACES,
  type WePostAppearance,
  type WePostLayout,
  type WePostPalette,
  type WePostPresentation,
  type WePostPreviewSize,
  type WePostTypeface,
} from './types';

export interface WePostPresentationSelection extends WePostPresentation {
  previewSize: WePostPreviewSize;
}

type WePostPresentationOption =
  | WePostLayout
  | WePostPalette
  | WePostAppearance
  | WePostTypeface
  | WePostPreviewSize;

const LABELS: Record<WePostPresentationOption, string> = {
  'brand-default': 'Brand Default',
  'field-notes': 'Field Notes',
  'editorial-feature': 'Editorial Feature',
  'brand-blue': 'Brand Blue',
  'paper-neutral': 'Paper Neutral',
  'warm-terracotta': 'Warm Terracotta',
  light: 'Light',
  dark: 'Dark',
  'modern-sans': 'Modern Sans',
  'editorial-serif': 'Editorial Serif',
  'humanist-mix': 'Humanist Mix',
  'mobile-390': 'Mobile 390px',
  'desktop-760': 'Desktop 760px',
};

function Control<Option extends WePostPresentationOption>({
  id,
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  value: Option;
  options: readonly Option[];
  disabled: boolean;
  onChange: (value: Option) => void;
}) {
  return (
    <label
      className='grid gap-1.5 text-sm font-medium text-slate-700'
      htmlFor={id}
    >
      {label}
      <select
        id={id}
        className='min-w-40 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100'
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as Option)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {LABELS[option]}
          </option>
        ))}
      </select>
    </label>
  );
}

export function WePostPresentationControls({
  value,
  disabled = false,
  onChange,
  onReset,
}: {
  value: WePostPresentationSelection;
  disabled?: boolean;
  onChange: (value: WePostPresentationSelection) => void;
  onReset: () => void;
}) {
  return (
    <section
      className='mb-10 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5'
      aria-label='Renderer presentation controls'
    >
      <div className='flex flex-wrap items-end gap-4'>
        <Control
          id='wepost-layout'
          label='Layout'
          value={value.layout}
          options={WEPOST_LAYOUTS}
          disabled={disabled}
          onChange={(layout) => onChange({ ...value, layout })}
        />
        <Control
          id='wepost-palette'
          label='Color palette'
          value={value.palette}
          options={WEPOST_PALETTES}
          disabled={disabled}
          onChange={(palette) => onChange({ ...value, palette })}
        />
        <Control
          id='wepost-appearance'
          label='Appearance'
          value={value.appearance}
          options={WEPOST_APPEARANCES}
          disabled={disabled}
          onChange={(appearance) => onChange({ ...value, appearance })}
        />
        <Control
          id='wepost-typeface'
          label='Typeface'
          value={value.typeface}
          options={WEPOST_TYPEFACES}
          disabled={disabled}
          onChange={(typeface) => onChange({ ...value, typeface })}
        />
        <Control
          id='wepost-preview-size'
          label='Preview size'
          value={value.previewSize}
          options={WEPOST_PREVIEW_SIZES}
          disabled={disabled}
          onChange={(previewSize) => onChange({ ...value, previewSize })}
        />
        <button
          className='inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50'
          type='button'
          disabled={disabled}
          onClick={onReset}
        >
          <RotateCcw className='h-4 w-4' />
          Reset
        </button>
      </div>
      <p className='mt-4 text-sm text-slate-500' data-testid='current-style'>
        {LABELS[value.layout]} · {LABELS[value.palette]} ·{' '}
        {LABELS[value.appearance]} · {LABELS[value.typeface]} ·{' '}
        {LABELS[value.previewSize]}
      </p>
    </section>
  );
}
