'use client';

import {
  Eye,
  Loader2,
  Monitor,
  Pencil,
  RefreshCw,
  Save,
  Smartphone,
  Sparkles,
} from 'lucide-react';

import type {
  WxPostAppearance,
  WxPostLayout,
  WxPostPalette,
  WxPostPresentation,
  WxPostPreviewSize,
  WxPostTypeface,
} from '@/components/wxpost/types';

import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';

export type DraftMode = 'edit' | 'preview';

const PRESENTATION_LABELS = {
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
} as const;

function PresentationSelect<
  Value extends
    | WxPostLayout
    | WxPostPalette
    | WxPostAppearance
    | WxPostTypeface,
>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: Value;
  options: readonly Value[];
  onChange: (value: Value) => void;
}) {
  return (
    <label className='grid min-w-0 gap-1 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500 sm:shrink-0'>
      {label}
      <select
        className='h-9 min-w-0 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold normal-case tracking-normal text-slate-700 outline-none transition hover:border-slate-300 focus:border-blue-500 sm:min-w-32'
        value={value}
        onChange={(event) => onChange(event.target.value as Value)}
        data-testid={`draft-${label.toLowerCase()}-select`}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {PRESENTATION_LABELS[option]}
          </option>
        ))}
      </select>
    </label>
  );
}

export function WxPostDraftControls({
  draftVersion,
  dirty,
  mode,
  presentation,
  previewSize,
  mobileHermesOpen,
  regeneratePending,
  chatPending,
  savePending,
  onModeChange,
  onPresentationChange,
  onPreviewSizeChange,
  onOpenHermes,
  onRegenerate,
  onSave,
}: {
  draftVersion: number;
  dirty: boolean;
  mode: DraftMode;
  presentation: WxPostPresentation;
  previewSize: WxPostPreviewSize;
  mobileHermesOpen: boolean;
  regeneratePending: boolean;
  chatPending: boolean;
  savePending: boolean;
  onModeChange: (mode: DraftMode) => void;
  onPresentationChange: (presentation: WxPostPresentation) => void;
  onPreviewSizeChange: (size: WxPostPreviewSize) => void;
  onOpenHermes: () => void;
  onRegenerate: () => void;
  onSave: () => void;
}) {
  return (
    <header className='grid gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm sm:px-4'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div className='min-w-0'>
          <div className='flex flex-wrap items-center gap-2'>
            <strong className='text-sm text-slate-900'>
              English Draft · v{draftVersion}
            </strong>
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-bold ${
                dirty
                  ? 'bg-amber-50 text-amber-700'
                  : 'bg-emerald-50 text-emerald-700'
              }`}
            >
              {dirty ? 'Unsaved changes' : '✓ Saved'}
            </span>
          </div>
          <p className='mb-0 mt-1 hidden text-xs text-slate-500 sm:block'>
            {mode === 'edit'
              ? 'Click a title or section to edit · Select text to ask Hermes'
              : 'Clean preview of the current Draft working copy'}
          </p>
        </div>
        <div className='flex items-center gap-2 max-[560px]:w-full'>
          <div
            className='flex h-10 rounded-lg bg-slate-100 p-1'
            aria-label='Draft mode'
          >
            <button
              type='button'
              className={`inline-flex items-center gap-1.5 rounded-md px-3 text-xs font-bold transition ${
                mode === 'edit'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500'
              }`}
              aria-pressed={mode === 'edit'}
              onClick={() => onModeChange('edit')}
              data-testid='draft-mode-edit'
            >
              <Pencil className='h-3.5 w-3.5' />
              Edit
            </button>
            <button
              type='button'
              className={`inline-flex items-center gap-1.5 rounded-md px-3 text-xs font-bold transition ${
                mode === 'preview'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500'
              }`}
              aria-pressed={mode === 'preview'}
              onClick={() => onModeChange('preview')}
              data-testid='draft-mode-preview'
            >
              <Eye className='h-3.5 w-3.5' />
              Preview
            </button>
          </div>
          <div className='ml-auto flex gap-2'>
            {mode === 'edit' && !mobileHermesOpen && (
              <button
                type='button'
                className={`${SECONDARY_BUTTON_CLASS} max-[480px]:min-h-10 max-[480px]:px-3 lg:hidden`}
                aria-label='Ask Hermes'
                onClick={onOpenHermes}
                data-testid='open-mobile-hermes'
              >
                <Sparkles />
                <span className='max-[560px]:sr-only'>Ask Hermes</span>
              </button>
            )}
            <button
              type='button'
              className={`${SECONDARY_BUTTON_CLASS} max-[480px]:min-h-10 max-[480px]:px-3`}
              disabled={
                dirty || regeneratePending || chatPending || savePending
              }
              title={
                dirty
                  ? 'Save or discard local edits before regenerating.'
                  : undefined
              }
              onClick={onRegenerate}
              data-testid='regenerate-draft'
            >
              {regeneratePending ? (
                <Loader2 className='animate-spin' />
              ) : (
                <RefreshCw />
              )}
              <span className='max-[430px]:sr-only'>Regenerate</span>
            </button>
            <button
              type='button'
              className={`${PRIMARY_BUTTON_CLASS} max-[480px]:min-h-10 max-[480px]:px-3`}
              disabled={!dirty || savePending || chatPending}
              onClick={onSave}
              data-testid='save-draft'
            >
              {savePending ? <Loader2 className='animate-spin' /> : <Save />}
              <span className='max-[430px]:sr-only'>Save Draft</span>
            </button>
          </div>
        </div>
      </div>

      <div
        className='grid grid-cols-2 items-end gap-3 border-t border-slate-100 pt-3 sm:flex'
        data-testid='draft-presentation-controls'
      >
        <PresentationSelect
          label='Layout'
          value={presentation.layout}
          options={
            ['brand-default', 'field-notes', 'editorial-feature'] as const
          }
          onChange={(layout) =>
            onPresentationChange({ ...presentation, layout })
          }
        />
        <PresentationSelect
          label='Palette'
          value={presentation.palette}
          options={['brand-blue', 'paper-neutral', 'warm-terracotta'] as const}
          onChange={(palette) =>
            onPresentationChange({ ...presentation, palette })
          }
        />
        <PresentationSelect
          label='Appearance'
          value={presentation.appearance}
          options={['light', 'dark'] as const}
          onChange={(appearance) =>
            onPresentationChange({ ...presentation, appearance })
          }
        />
        <PresentationSelect
          label='Typeface'
          value={presentation.typeface}
          options={['modern-sans', 'editorial-serif', 'humanist-mix'] as const}
          onChange={(typeface) =>
            onPresentationChange({ ...presentation, typeface })
          }
        />
        <div className='col-span-2 grid gap-1 sm:col-span-1 sm:shrink-0'>
          <span className='text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500'>
            Canvas
          </span>
          <div className='flex h-9 rounded-lg border border-slate-200 bg-slate-50 p-0.5'>
            <button
              type='button'
              className={`grid w-10 place-items-center rounded-md ${
                previewSize === 'desktop-760'
                  ? 'bg-white text-blue-600 shadow-sm'
                  : 'text-slate-500'
              }`}
              aria-label='Desktop canvas'
              aria-pressed={previewSize === 'desktop-760'}
              onClick={() => onPreviewSizeChange('desktop-760')}
              data-testid='draft-canvas-desktop'
            >
              <Monitor className='h-4 w-4' />
            </button>
            <button
              type='button'
              className={`grid w-10 place-items-center rounded-md ${
                previewSize === 'mobile-390'
                  ? 'bg-white text-blue-600 shadow-sm'
                  : 'text-slate-500'
              }`}
              aria-label='Mobile canvas'
              aria-pressed={previewSize === 'mobile-390'}
              onClick={() => onPreviewSizeChange('mobile-390')}
              data-testid='draft-canvas-mobile'
            >
              <Smartphone className='h-4 w-4' />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
