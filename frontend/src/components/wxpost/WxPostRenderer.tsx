'use client';

import { memo, useEffect, useMemo, useRef } from 'react';

import { compileWxPost } from './renderer/compiler';
import { editableElementToMarkdown } from './renderer/editorMarkdown';
import { parseWxPostEditKey } from './renderer/editing';
import type {
  WxPostPresentation,
  WxPostPreviewSize,
  WxPostRenderContext,
  WxPostRenderDocument,
} from './types';
import type { WxPostMediaDeleteTarget } from './renderer/editing';

interface WxPostRendererProps {
  article: WxPostRenderDocument;
  presentation?: WxPostPresentation;
  previewSize?: WxPostPreviewSize;
  context?: WxPostRenderContext;
  className?: string;
  editor?: {
    activeKey: string | null;
    onSelect: (key: string) => void;
    onBlur: () => void;
    onChange: (key: string, value: string) => string | null;
    onDeleteMedia: (target: WxPostMediaDeleteTarget) => void;
    onDeleteDirectiveItem: (key: string) => void;
  };
}

const RendererMarkup = memo(
  function RendererMarkup({ html }: { html: string; frozen: boolean }) {
    return (
      <div className='contents' dangerouslySetInnerHTML={{ __html: html }} />
    );
  },
  (previous, next) => next.frozen || previous.html === next.html
);

export function WxPostRenderer({
  article,
  presentation = article.presentation,
  previewSize = 'mobile-390',
  context = {},
  className = '',
  editor,
}: WxPostRendererProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const editable = Boolean(editor);
  const compiled = useMemo(
    () =>
      compileWxPost(
        {
          renderDocument: article,
          presentation,
          context,
        },
        { editable }
      ),
    [article, context, editable, presentation]
  );

  useEffect(() => {
    const root = rootRef.current;
    const activeKey = editor?.activeKey;
    if (!root || !activeKey) return;
    const target = Array.from(
      root.querySelectorAll<HTMLElement>('[data-wxpost-edit-key]')
    ).find((element) => element.dataset.wxpostEditKey === activeKey);
    if (!target) return;
    const targetOutline = target.style.outline;
    const targetOutlineOffset = target.style.outlineOffset;
    target.contentEditable = 'true';
    target.setAttribute('role', 'textbox');
    const targetType = parseWxPostEditKey(activeKey);
    target.setAttribute(
      'aria-multiline',
      String(targetType.kind === 'markdown')
    );
    target.setAttribute(
      'aria-label',
      `Edit ${target.dataset.wxpostEditLabel ?? 'draft text'}`
    );
    target.dataset.wxpostLastValidText = target.textContent ?? '';
    target.style.outline = '2px solid #3b82f6';
    target.style.outlineOffset = '2px';
    target.focus({ preventScroll: true });
    return () => {
      target.contentEditable = 'false';
      target.removeAttribute('role');
      target.removeAttribute('aria-multiline');
      target.removeAttribute('aria-label');
      delete target.dataset.wxpostLastValidText;
      target.style.outline = targetOutline;
      target.style.outlineOffset = targetOutlineOffset;
    };
  }, [editor?.activeKey]);

  return (
    <div
      ref={rootRef}
      className={`mx-auto w-full ${
        previewSize === 'mobile-390' ? 'max-w-[390px]' : 'max-w-[760px]'
      } [&_[data-wxpost-edit-key]]:cursor-text [&_[data-wxpost-edit-key]]:outline-offset-2 [&_[data-wxpost-edit-key]:hover]:outline [&_[data-wxpost-edit-key]:hover]:outline-1 [&_[data-wxpost-edit-key]:hover]:outline-blue-300 [&_[data-wxpost-delete-media]]:pointer-events-none [&_[data-wxpost-delete-media]]:opacity-0 [&_[data-wxpost-delete-media]]:transition-opacity [&_[data-wxpost-media-frame]:focus-within_[data-wxpost-delete-media]]:pointer-events-auto [&_[data-wxpost-media-frame]:focus-within_[data-wxpost-delete-media]]:opacity-100 [&_[data-wxpost-media-frame]:hover_[data-wxpost-delete-media]]:pointer-events-auto [&_[data-wxpost-media-frame]:hover_[data-wxpost-delete-media]]:opacity-100 [&_[data-wxpost-delete-item]]:pointer-events-none [&_[data-wxpost-delete-item]]:opacity-0 [&_[data-wxpost-delete-item]]:transition-opacity [&_[data-wxpost-item-container]:focus-within_[data-wxpost-delete-item]]:pointer-events-auto [&_[data-wxpost-item-container]:focus-within_[data-wxpost-delete-item]]:opacity-100 [&_[data-wxpost-item-container]:hover_[data-wxpost-delete-item]]:pointer-events-auto [&_[data-wxpost-item-container]:hover_[data-wxpost-delete-item]]:opacity-100 ${className}`}
      data-testid='wxpost-stage'
      data-preview-size={previewSize}
      onMouseDown={(event) => {
        if (!editor) return;
        if (
          (event.target as Element).closest(
            '[data-wxpost-delete-media],[data-wxpost-delete-item]'
          )
        ) {
          event.preventDefault();
          return;
        }
        const target = (event.target as Element).closest<HTMLElement>(
          '[data-wxpost-edit-key]'
        );
        const key = target?.dataset.wxpostEditKey;
        if (!key || key === editor.activeKey) return;
        // Make the clicked block focusable before the browser places the
        // caret, then let React attach the editor semantics and active outline.
        target.contentEditable = 'true';
        editor.onSelect(key);
      }}
      onBlur={() => {
        if (!editor) return;
        window.requestAnimationFrame(() => {
          if (!rootRef.current?.contains(document.activeElement)) {
            editor.onBlur();
          }
        });
      }}
      onClick={(event) => {
        if (!editor) return;
        const target = event.target as Element;
        const deleteButton = target.closest<HTMLElement>(
          '[data-wxpost-delete-media]'
        );
        if (
          deleteButton?.dataset.wxpostDeleteMedia &&
          deleteButton.dataset.wxpostDeleteKey
        ) {
          event.preventDefault();
          event.stopPropagation();
          editor.onDeleteMedia({
            mediaId: deleteButton.dataset.wxpostDeleteMedia,
            key: deleteButton.dataset.wxpostDeleteKey,
          });
          return;
        }
        const deleteItemButton = target.closest<HTMLElement>(
          '[data-wxpost-delete-item]'
        );
        if (deleteItemButton?.dataset.wxpostDeleteItem) {
          event.preventDefault();
          event.stopPropagation();
          editor.onDeleteDirectiveItem(
            deleteItemButton.dataset.wxpostDeleteItem
          );
          return;
        }
        const editable = target.closest<HTMLElement>('[data-wxpost-edit-key]');
        if (editable?.dataset.wxpostEditKey) {
          editor.onSelect(editable.dataset.wxpostEditKey);
          return;
        }
        editor.onBlur();
      }}
      onInput={(event) => {
        if (!editor) return;
        const target = event.target as HTMLElement;
        const editable = target.closest<HTMLElement>('[data-wxpost-edit-key]');
        const key = editable?.dataset.wxpostEditKey;
        if (!editable || !key) return;
        const editTarget = parseWxPostEditKey(key);
        const value =
          editTarget.kind === 'markdown'
            ? editableElementToMarkdown(editable)
            : (editable.textContent ?? '');
        const validationError = editor.onChange(key, value);
        if (!validationError) {
          editable.dataset.wxpostLastValidText = editable.textContent ?? '';
          return;
        }
        editable.textContent = editable.dataset.wxpostLastValidText ?? '';
        const selection = window.getSelection();
        if (selection) {
          const range = document.createRange();
          range.selectNodeContents(editable);
          range.collapse(false);
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }}
      onKeyDown={(event) => {
        if (!editor || event.key !== 'Enter') return;
        const target = (event.target as HTMLElement).closest<HTMLElement>(
          '[data-wxpost-edit-key]'
        );
        const key = target?.dataset.wxpostEditKey;
        if (!key || parseWxPostEditKey(key).kind === 'markdown') return;
        event.preventDefault();
        editor.onBlur();
      }}
    >
      <RendererMarkup
        html={compiled.html}
        frozen={Boolean(editor && editor.activeKey !== null)}
      />
    </div>
  );
}
