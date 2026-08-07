'use client';

import { ChevronUp, RotateCcw, SlidersHorizontal, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import {
  formatWxPostPresentationSelection,
  type WxPostPresentationSelection,
  WxPostPresentationOptions,
  type WxPostRenderModeControl,
  WxPostRendererControlGroup,
} from './WxPostPresentationControls';

export function WxPostPresentationDrawer({
  value,
  onChange,
  onReset,
  renderMode,
  onRenderModeChange,
  charCounts,
}: {
  value: WxPostPresentationSelection;
  onChange: (value: WxPostPresentationSelection) => void;
  onReset: () => void;
} & WxPostRenderModeControl) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const summary = formatWxPostPresentationSelection(value);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const desktopMedia = window.matchMedia('(min-width: 640px)');
    if (desktopMedia.matches) {
      setIsOpen(false);
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        triggerRef.current?.focus();
        return;
      }

      if (event.key !== 'Tab' || !dialogRef.current) return;

      const dialog = dialogRef.current;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter((element) => element.offsetParent !== null);
      const first = focusable.at(0);
      const last = focusable.at(-1);
      if (!first || !last) {
        event.preventDefault();
        return;
      }

      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (active === last || !dialog.contains(active))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    const handleBreakpointChange = (event: MediaQueryListEvent) => {
      if (event.matches) setIsOpen(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    desktopMedia.addEventListener('change', handleBreakpointChange);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
      desktopMedia.removeEventListener('change', handleBreakpointChange);
    };
  }, [isOpen]);

  const close = () => {
    setIsOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };

  return (
    <>
      <div className='sticky top-20 z-30 mb-6 sm:hidden'>
        <button
          ref={triggerRef}
          className='flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-white/95 p-2.5 text-left shadow-sm backdrop-blur transition hover:border-slate-300 hover:shadow-md'
          type='button'
          aria-haspopup='dialog'
          aria-expanded={isOpen}
          aria-label={`Customize article appearance. Current style: ${summary}`}
          onClick={() => setIsOpen(true)}
        >
          <span className='grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-blue-600 to-purple-600 text-white shadow-sm'>
            <SlidersHorizontal className='h-4 w-4' aria-hidden='true' />
          </span>
          <span className='min-w-0 flex-1'>
            <span className='block text-xs font-semibold text-slate-900'>
              Article style
            </span>
            <span
              className='mt-0.5 block truncate text-xs text-slate-500'
              data-testid='mobile-style-summary'
            >
              {summary}
            </span>
          </span>
          <span className='inline-flex shrink-0 items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1.5 text-xs font-semibold text-slate-700'>
            Customize
            <ChevronUp className='h-3.5 w-3.5' aria-hidden='true' />
          </span>
        </button>
      </div>

      {isMounted &&
        isOpen &&
        createPortal(
          <div
            className='fixed inset-0 z-[80] flex items-end bg-slate-950/45 backdrop-blur-[2px] sm:hidden'
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) close();
            }}
          >
            <section
              ref={dialogRef}
              className='flex max-h-[88dvh] w-full flex-col overflow-hidden rounded-t-[1.75rem] bg-white shadow-2xl'
              role='dialog'
              aria-modal='true'
              aria-labelledby='wxpost-appearance-title'
            >
              <div className='px-4 pt-3'>
                <div
                  className='mx-auto h-1 w-10 rounded-full bg-slate-300'
                  aria-hidden='true'
                />
                <div className='flex items-start justify-between gap-4 py-4'>
                  <div>
                    <h2
                      className='text-base font-semibold text-slate-950'
                      id='wxpost-appearance-title'
                    >
                      Customize appearance
                    </h2>
                    <p className='mt-1 text-sm text-slate-500'>
                      Changes apply only to this preview.
                    </p>
                  </div>
                  <button
                    ref={closeRef}
                    className='grid h-9 w-9 shrink-0 place-items-center rounded-full border border-slate-200 text-slate-500 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900'
                    type='button'
                    aria-label='Close appearance settings'
                    onClick={close}
                  >
                    <X className='h-4 w-4' aria-hidden='true' />
                  </button>
                </div>
              </div>

              <div className='min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-5'>
                <WxPostRendererControlGroup
                  renderMode={renderMode}
                  onRenderModeChange={onRenderModeChange}
                  charCounts={charCounts}
                  className='mb-6'
                />
                <WxPostPresentationOptions value={value} onChange={onChange} />
              </div>

              <div className='flex gap-3 border-t border-slate-200 bg-white px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-3'>
                <button
                  className='inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50'
                  type='button'
                  onClick={onReset}
                >
                  <RotateCcw className='h-4 w-4' aria-hidden='true' />
                  Reset
                </button>
                <button
                  className='flex-[1.5] rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:from-blue-700 hover:to-purple-700 hover:shadow-md'
                  type='button'
                  onClick={close}
                >
                  Done
                </button>
              </div>
            </section>
          </div>,
          document.body
        )}
    </>
  );
}
