'use client';

import { useEffect, useRef, useState } from 'react';

import {
  Check,
  ChevronDown,
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
  menuAlign = 'start',
  onChange,
}: {
  label: string;
  value: Value;
  options: readonly Value[];
  menuAlign?: 'start' | 'end';
  onChange: (value: Value) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  return (
    <div
      className='relative grid min-w-0 gap-1 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500 min-[761px]:min-w-32 min-[761px]:shrink-0'
      ref={containerRef}
    >
      <span>{label}</span>
      <button
        type='button'
        className='relative flex h-9 min-w-0 w-full items-center rounded-md border border-gray-300 bg-white py-1.5 pl-3 pr-9 text-left text-sm font-normal normal-case tracking-normal text-gray-900 outline-none transition-colors duration-200 hover:border-gray-400 focus-visible:border-blue-500 focus-visible:outline-none aria-expanded:border-blue-500'
        aria-label={label}
        aria-haspopup='listbox'
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        data-testid={`draft-${label.toLowerCase()}-select`}
      >
        <span className='min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap'>
          {PRESENTATION_LABELS[value]}
        </span>
        <ChevronDown
          className={`pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 transition-transform duration-150 ${
            open ? '-translate-y-1/2 rotate-180' : ''
          }`}
          aria-hidden='true'
        />
      </button>

      {open && (
        <div
          className={`absolute top-[calc(100%+6px)] z-40 w-[180px] min-w-full max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-gray-300 bg-white p-1 shadow-xl ${
            menuAlign === 'end' ? 'right-0' : 'left-0'
          }`}
        >
          <div role='listbox' aria-label={label}>
            {options.map((option) => {
              const selected = option === value;
              return (
                <button
                  key={option}
                  type='button'
                  role='option'
                  aria-selected={selected}
                  className={`flex min-h-9 w-full items-center justify-between gap-2 rounded px-2.5 py-2 text-left text-sm font-normal normal-case tracking-normal transition-colors ${
                    selected
                      ? 'bg-[#e8efff] font-semibold text-blue-700'
                      : 'text-slate-700 hover:bg-slate-100'
                  }`}
                  onClick={() => {
                    onChange(option);
                    setOpen(false);
                  }}
                  data-testid={`draft-${label.toLowerCase()}-option-${option}`}
                >
                  <span className='whitespace-nowrap'>
                    {PRESENTATION_LABELS[option]}
                  </span>
                  {selected && (
                    <Check className='h-4 w-4 shrink-0' aria-hidden='true' />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
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
              Draft · v{draftVersion}
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
              ? 'Click a title or section to edit · Select text to ask the assistant'
              : 'Clean preview of the current Draft working copy'}
          </p>
        </div>
        <div className='flex items-center gap-2 max-[760px]:w-full'>
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
              <span className='max-[360px]:sr-only'>Edit</span>
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
              <span className='max-[360px]:sr-only'>Preview</span>
            </button>
          </div>
          <div className='ml-auto flex gap-2'>
            {mode === 'edit' && !mobileHermesOpen && (
              <button
                type='button'
                className={`${SECONDARY_BUTTON_CLASS} max-[760px]:min-h-10 max-[760px]:px-3 lg:hidden`}
                aria-label='Ask the assistant'
                onClick={onOpenHermes}
                data-testid='open-mobile-hermes'
              >
                <Sparkles />
                <span className='max-[760px]:sr-only'>Ask the assistant</span>
              </button>
            )}
            <button
              type='button'
              className={`${SECONDARY_BUTTON_CLASS} max-[760px]:min-h-10 max-[760px]:px-3`}
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
              <span className='max-[760px]:sr-only'>Regenerate</span>
            </button>
            <button
              type='button'
              className={`${PRIMARY_BUTTON_CLASS} max-[760px]:min-h-10 max-[760px]:px-3`}
              disabled={!dirty || savePending || chatPending}
              onClick={onSave}
              data-testid='save-draft'
            >
              {savePending ? <Loader2 className='animate-spin' /> : <Save />}
              <span className='max-[760px]:sr-only'>Save Draft</span>
            </button>
          </div>
        </div>
      </div>

      <div
        className='grid grid-cols-2 items-end gap-3 border-t border-slate-100 pt-3 min-[761px]:flex'
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
          menuAlign='end'
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
          menuAlign='end'
          onChange={(typeface) =>
            onPresentationChange({ ...presentation, typeface })
          }
        />
        <div className='col-span-2 grid gap-1 min-[761px]:col-span-1 min-[761px]:shrink-0'>
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
