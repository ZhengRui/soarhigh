'use client';

import { useEffect } from 'react';

const MEDIA_PATH = '/api/wxpost/draft-preview/';

function isDraftImage(node: EventTarget | null): node is HTMLImageElement {
  return node instanceof HTMLImageElement && node.src.includes(MEDIA_PATH);
}

function showRetry(img: HTMLImageElement) {
  if (!img.parentElement) return;
  const box = document.createElement('div');
  // The image's own inline styles carry the exact aspect-ratio box and
  // palette border, so the placeholder occupies the identical space.
  box.style.cssText = img.style.cssText;
  box.style.display = 'grid';
  box.style.placeItems = 'center';
  box.style.background = 'rgba(148, 163, 184, 0.12)';
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Retry image';
  button.className =
    'rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm ' +
    'font-medium text-slate-700 shadow-sm hover:bg-slate-50';
  box.appendChild(button);
  button.addEventListener('click', () => {
    const retry = img.cloneNode(false) as HTMLImageElement;
    retry.loading = 'eager';
    try {
      const url = new URL(img.src);
      url.searchParams.set('r', String(Date.now()));
      retry.src = url.toString();
    } catch {
      retry.src = img.src;
    }
    box.replaceWith(retry);
  });
  img.replaceWith(box);
}

/**
 * Failed-image recovery for the static compiled article HTML.
 *
 * Mounted as a client component so the effect runs only AFTER React
 * hydration commits: swapping DOM inside the dangerouslySetInnerHTML
 * container before that point makes hydration fail and React regenerate
 * the tree, discarding the placeholders (and their click handlers).
 * The mount-time sweep picks up images that failed before the effect ran;
 * the capture-phase listener covers later failures and retried images.
 */
export function MediaRetryActivator() {
  useEffect(() => {
    const onError = (event: Event) => {
      if (isDraftImage(event.target)) showRetry(event.target);
    };
    document.addEventListener('error', onError, true);
    for (const img of Array.from(document.querySelectorAll('img'))) {
      if (isDraftImage(img) && img.complete && img.naturalWidth === 0) {
        showRetry(img);
      }
    }
    return () => document.removeEventListener('error', onError, true);
  }, []);
  return null;
}
