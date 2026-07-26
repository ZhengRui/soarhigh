'use client';

import { RotateCcw } from 'lucide-react';

import {
  WXPOST_APPEARANCES,
  WXPOST_LAYOUTS,
  WXPOST_PALETTES,
  WXPOST_PREVIEW_SIZES,
  WXPOST_TYPEFACES,
  type WxPostAppearance,
  type WxPostLayout,
  type WxPostPalette,
  type WxPostPresentation,
  type WxPostPreviewSize,
  type WxPostTypeface,
} from './types';

export interface WxPostPresentationSelection extends WxPostPresentation {
  previewSize: WxPostPreviewSize;
}

type WxPostPresentationOption =
  | WxPostLayout
  | WxPostPalette
  | WxPostAppearance
  | WxPostTypeface
  | WxPostPreviewSize;

const LABELS: Record<WxPostPresentationOption, string> = {
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

function Control<Option extends WxPostPresentationOption>({
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

export function WxPostPresentationControls({
  value,
  disabled = false,
  onChange,
  onReset,
}: {
  value: WxPostPresentationSelection;
  disabled?: boolean;
  onChange: (value: WxPostPresentationSelection) => void;
  onReset: () => void;
}) {
  return (
    <section
      className='mb-10 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5'
      aria-label='Renderer presentation controls'
    >
      <div className='flex flex-wrap items-end gap-4'>
        <Control
          id='wxpost-layout'
          label='Layout'
          value={value.layout}
          options={WXPOST_LAYOUTS}
          disabled={disabled}
          onChange={(layout) => onChange({ ...value, layout })}
        />
        <Control
          id='wxpost-palette'
          label='Color palette'
          value={value.palette}
          options={WXPOST_PALETTES}
          disabled={disabled}
          onChange={(palette) => onChange({ ...value, palette })}
        />
        <Control
          id='wxpost-appearance'
          label='Appearance'
          value={value.appearance}
          options={WXPOST_APPEARANCES}
          disabled={disabled}
          onChange={(appearance) => onChange({ ...value, appearance })}
        />
        <Control
          id='wxpost-typeface'
          label='Typeface'
          value={value.typeface}
          options={WXPOST_TYPEFACES}
          disabled={disabled}
          onChange={(typeface) => onChange({ ...value, typeface })}
        />
        <Control
          id='wxpost-preview-size'
          label='Preview size'
          value={value.previewSize}
          options={WXPOST_PREVIEW_SIZES}
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
