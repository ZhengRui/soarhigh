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

const LAYOUT_DESCRIPTIONS: Record<WxPostLayout, string> = {
  'brand-default': 'Clear rhythm for meeting recaps and practical guides.',
  'field-notes': 'Observational, immediate, and suited to on-site stories.',
  'editorial-feature': 'Magazine-like hierarchy for people and long reads.',
};

const PALETTE_SWATCHES: Record<WxPostPalette, readonly string[]> = {
  'brand-blue': ['#2563eb', '#7c3aed', '#eef2ff'],
  'paper-neutral': ['#2d2b27', '#9b9285', '#f8f6f0'],
  'warm-terracotta': ['#d8653b', '#e9a23b', '#fff0dd'],
};

export function formatWxPostPresentationSelection(
  value: WxPostPresentationSelection
) {
  return [
    LABELS[value.layout],
    LABELS[value.palette],
    LABELS[value.appearance],
    LABELS[value.typeface],
    LABELS[value.previewSize],
  ].join(' · ');
}

function OptionButton<Option extends WxPostPresentationOption>({
  group,
  option,
  selected,
  disabled,
  className = '',
  children,
  onSelect,
}: {
  group: string;
  option: Option;
  selected: boolean;
  disabled: boolean;
  className?: string;
  children: React.ReactNode;
  onSelect: (option: Option) => void;
}) {
  return (
    <button
      className={`rounded-xl border text-left transition ${
        selected
          ? 'border-blue-600 bg-blue-50 text-slate-950'
          : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900'
      } ${className}`}
      type='button'
      disabled={disabled}
      aria-pressed={selected}
      data-testid={`wxpost-${group}-${option}`}
      onClick={() => onSelect(option)}
    >
      {children}
    </button>
  );
}

function ControlGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className='min-w-0'>
      <legend className='mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500'>
        {title}
      </legend>
      {children}
    </fieldset>
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
      className='mb-10 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6'
      aria-label='Article presentation'
    >
      <div className='mb-5 flex items-start justify-between gap-4'>
        <div>
          <p className='text-sm font-semibold text-slate-900'>
            Make this preview yours
          </p>
          <p className='mt-1 text-sm text-slate-500'>
            These choices stay in your browser and do not change the article.
          </p>
        </div>
        <button
          className='inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-900'
          type='button'
          disabled={disabled}
          onClick={onReset}
        >
          <RotateCcw className='h-3.5 w-3.5' />
          Reset
        </button>
      </div>

      <WxPostPresentationOptions
        value={value}
        disabled={disabled}
        onChange={onChange}
      />
    </section>
  );
}

export function WxPostPresentationOptions({
  value,
  disabled = false,
  onChange,
}: {
  value: WxPostPresentationSelection;
  disabled?: boolean;
  onChange: (value: WxPostPresentationSelection) => void;
}) {
  return (
    <>
      <div className='grid gap-6'>
        <ControlGroup title='Layout'>
          <div className='grid gap-2 sm:grid-cols-3'>
            {WXPOST_LAYOUTS.map((layout) => (
              <OptionButton
                key={layout}
                group='layout'
                option={layout}
                selected={value.layout === layout}
                disabled={disabled}
                className='p-3'
                onSelect={(next) => onChange({ ...value, layout: next })}
              >
                <span className='block text-sm font-semibold'>
                  {LABELS[layout]}
                </span>
                <span className='mt-1 block text-xs leading-5 text-slate-500'>
                  {LAYOUT_DESCRIPTIONS[layout]}
                </span>
              </OptionButton>
            ))}
          </div>
        </ControlGroup>

        <ControlGroup title='Color palette'>
          <div className='grid gap-2 sm:grid-cols-3'>
            {WXPOST_PALETTES.map((palette) => (
              <OptionButton
                key={palette}
                group='palette'
                option={palette}
                selected={value.palette === palette}
                disabled={disabled}
                className='flex items-center justify-between gap-3 p-3'
                onSelect={(next) => onChange({ ...value, palette: next })}
              >
                <span className='text-sm font-semibold'>{LABELS[palette]}</span>
                <span className='flex overflow-hidden rounded-full border border-black/10'>
                  {PALETTE_SWATCHES[palette].map((color) => (
                    <span
                      key={color}
                      className='h-5 w-5'
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </span>
              </OptionButton>
            ))}
          </div>
        </ControlGroup>

        <div className='grid gap-6 lg:grid-cols-[0.7fr_1.4fr_1fr]'>
          <ControlGroup title='Appearance'>
            <div className='grid grid-cols-2 gap-2'>
              {WXPOST_APPEARANCES.map((appearance) => (
                <OptionButton
                  key={appearance}
                  group='appearance'
                  option={appearance}
                  selected={value.appearance === appearance}
                  disabled={disabled}
                  className='px-3 py-2 text-center text-sm font-semibold'
                  onSelect={(next) => onChange({ ...value, appearance: next })}
                >
                  {LABELS[appearance]}
                </OptionButton>
              ))}
            </div>
          </ControlGroup>

          <ControlGroup title='Typeface'>
            <div className='grid grid-cols-3 gap-2'>
              {WXPOST_TYPEFACES.map((typeface) => (
                <OptionButton
                  key={typeface}
                  group='typeface'
                  option={typeface}
                  selected={value.typeface === typeface}
                  disabled={disabled}
                  className='px-2 py-2 text-center text-xs font-semibold sm:text-sm'
                  onSelect={(next) => onChange({ ...value, typeface: next })}
                >
                  <span
                    className={
                      typeface === 'modern-sans'
                        ? 'font-sans'
                        : typeface === 'editorial-serif'
                          ? 'font-serif'
                          : 'font-medium'
                    }
                  >
                    {LABELS[typeface]}
                  </span>
                </OptionButton>
              ))}
            </div>
          </ControlGroup>

          <ControlGroup title='Preview size'>
            <div className='grid grid-cols-2 gap-2'>
              {WXPOST_PREVIEW_SIZES.map((previewSize) => (
                <OptionButton
                  key={previewSize}
                  group='preview-size'
                  option={previewSize}
                  selected={value.previewSize === previewSize}
                  disabled={disabled}
                  className='px-2 py-2 text-center text-xs font-semibold sm:text-sm'
                  onSelect={(next) => onChange({ ...value, previewSize: next })}
                >
                  {previewSize === 'mobile-390' ? 'Mobile' : 'Desktop'}
                </OptionButton>
              ))}
            </div>
          </ControlGroup>
        </div>
      </div>

      <p className='mt-5 text-xs text-slate-500' data-testid='current-style'>
        {formatWxPostPresentationSelection(value)}
      </p>
    </>
  );
}
