'use client';

import type {
  PointerEvent as ReactPointerEvent,
  TextareaHTMLAttributes,
} from 'react';
import { useLayoutEffect, useRef } from 'react';

interface ResizableTextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  resizeHandleTestId?: string;
}

interface ResizeState {
  pointerId: number;
  startHeight: number;
  startY: number;
  minHeight: number;
}

export function ResizableTextarea({
  className = '',
  resizeHandleTestId,
  ...props
}: ResizableTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const initialHeight = useRef(0);
  const resizeState = useRef<ResizeState | null>(null);

  useLayoutEffect(() => {
    const height = textareaRef.current?.offsetHeight ?? 0;
    if (height > 0) initialHeight.current = height;
  }, []);

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;

    const textarea = textareaRef.current;
    if (!textarea) return;

    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    if (initialHeight.current === 0) {
      initialHeight.current = textarea.offsetHeight;
    }
    resizeState.current = {
      pointerId: event.pointerId,
      startHeight: textarea.offsetHeight,
      startY: event.clientY,
      minHeight: initialHeight.current,
    };
  }

  function resize(event: ReactPointerEvent<HTMLDivElement>) {
    const state = resizeState.current;
    const textarea = textareaRef.current;
    if (!state || !textarea || state.pointerId !== event.pointerId) return;

    event.preventDefault();
    const nextHeight = Math.max(
      state.minHeight,
      state.startHeight + event.clientY - state.startY
    );
    textarea.style.height = `${nextHeight}px`;
  }

  function stopResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (resizeState.current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    resizeState.current = null;
  }

  return (
    <div className='group/resize relative'>
      <textarea
        ref={textareaRef}
        className={`${className} resize-none`}
        {...props}
      />
      <div
        className='absolute inset-x-0 bottom-0 flex h-6 touch-none cursor-ns-resize items-center justify-center'
        onPointerDown={startResize}
        onPointerMove={resize}
        onPointerUp={stopResize}
        onPointerCancel={stopResize}
        data-testid={resizeHandleTestId}
      >
        <span className='h-1 w-20 rounded-full bg-gray-300 transition-colors duration-200 group-hover/resize:bg-gray-400' />
      </div>
    </div>
  );
}
