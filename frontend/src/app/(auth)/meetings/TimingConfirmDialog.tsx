'use client';

import React from 'react';
import { createPortal } from 'react-dom';

interface TimingConfirmDialogProps {
  visible: boolean;
  title: string;
  message: React.ReactNode;
  confirmText: string;
  cancelText?: string;
  confirmDanger?: boolean;
  confirmDisabled?: boolean;
  cancelDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TimingConfirmDialog({
  visible,
  title,
  message,
  confirmText,
  cancelText = 'Cancel',
  confirmDanger = false,
  confirmDisabled = false,
  cancelDisabled = false,
  onConfirm,
  onCancel,
}: TimingConfirmDialogProps) {
  if (!visible || typeof window === 'undefined') {
    return null;
  }

  return createPortal(
    <div
      className='fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]'
      onClick={onCancel}
    >
      <div
        role='dialog'
        aria-modal='true'
        aria-labelledby='timing-confirm-title'
        className='bg-white rounded-lg p-6 mx-4 max-w-sm sm:max-w-md shadow-xl'
        onClick={(event) => event.stopPropagation()}
      >
        <h4
          id='timing-confirm-title'
          className='text-sm sm:text-base font-medium text-gray-900 mb-2'
        >
          {title}
        </h4>
        <div className='text-xs sm:text-sm text-gray-500 mb-4'>{message}</div>
        <div className='flex gap-3 justify-end'>
          <button
            type='button'
            onClick={onCancel}
            disabled={cancelDisabled}
            className='px-3 py-1.5 text-xs sm:text-sm text-gray-600 hover:text-gray-800 transition-colors disabled:opacity-50'
          >
            {cancelText}
          </button>
          <button
            type='button'
            onClick={onConfirm}
            disabled={confirmDisabled}
            className={`px-4 py-1.5 text-xs sm:text-sm text-white rounded-lg transition-colors disabled:opacity-50 ${
              confirmDanger
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-indigo-600 hover:bg-indigo-700'
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
