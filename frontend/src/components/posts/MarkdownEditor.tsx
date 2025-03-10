'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Check, Eye, Pencil, Lock, Globe } from 'lucide-react';
import toast from 'react-hot-toast';

// Dynamically import the markdown editor to avoid SSR issues
const MDEditor = dynamic(() => import('@uiw/react-md-editor'), {
  ssr: false,
  loading: () => (
    <div className='h-[400px] w-full bg-gray-100 rounded-md animate-pulse flex items-center justify-center'>
      <p className='text-gray-500'>Loading editor...</p>
    </div>
  ),
});

// Dynamically import the markdown renderer component
const MDPreview = dynamic(
  () => import('@uiw/react-md-editor').then((mod) => mod.default.Markdown),
  { ssr: false }
);

interface MarkdownEditorProps {
  initialValue?: string;
  onChange: (value: string) => void;
  isPublic: boolean;
  onVisibilityChange: (isPublic: boolean) => void;
  className?: string;
}

export const MarkdownEditor: React.FC<MarkdownEditorProps> = ({
  initialValue = '',
  onChange,
  isPublic,
  onVisibilityChange,
  className = '',
}) => {
  const [value, setValue] = useState(initialValue);
  const [previewMode, setPreviewMode] = useState<'edit' | 'preview'>('edit');

  // Add effect to update value when initialValue changes
  useEffect(() => {
    if (initialValue) {
      setValue(initialValue);
    }
  }, [initialValue]);

  const handleChange = (value?: string) => {
    if (value !== undefined) {
      setValue(value);
      onChange(value);
    }
  };

  const handleCopyToClipboard = () => {
    navigator.clipboard.writeText(value);
    toast.success('Copied to clipboard');
  };

  return (
    <div className={`flex flex-col space-y-4 ${className}`}>
      {/* Editor toolbar */}
      <div className='flex flex-col xs:flex-row xs:justify-between xs:items-center gap-4'>
        {/* Edit/Preview toggle */}
        <div className='flex space-x-2'>
          <button
            type='button'
            onClick={() => setPreviewMode('edit')}
            className={`px-2 py-1 xs:px-3 xs:py-1.5 rounded-md text-xs xs:text-sm font-medium flex items-center gap-1.5 transition-colors ${
              previewMode === 'edit'
                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            <Pencil className='w-3.5 h-3.5' />
            Edit
          </button>
          <button
            type='button'
            onClick={() => setPreviewMode('preview')}
            className={`px-2 py-1 xs:px-3 xs:py-1.5 rounded-md text-xs xs:text-sm font-medium flex items-center gap-1.5 transition-colors ${
              previewMode === 'preview'
                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            <Eye className='w-3.5 h-3.5' />
            Preview
          </button>
        </div>

        {/* Visibility toggle */}
        <div className='flex items-center'>
          {/* <span className='text-xs sm:text-sm text-gray-500 mr-2'>
            Visibility:
          </span> */}
          <button
            type='button'
            onClick={() => onVisibilityChange(true)}
            className={`px-2 py-1 xs:px-3 xs:py-1.5 rounded-l-md text-xs xs:text-sm font-medium flex items-center gap-1.5 transition-colors border ${
              isPublic
                ? 'bg-green-50 text-green-700 border-green-200'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 border-r border-r-red-200'
            }`}
          >
            <Globe className='w-3.5 h-3.5' />
            <span className='whitespace-nowrap'>Public</span>
            {isPublic && <Check className='w-3.5 h-3.5 ml-1' />}
          </button>
          <button
            type='button'
            onClick={() => onVisibilityChange(false)}
            className={`px-2 py-1 xs:px-3 xs:py-1.5 rounded-r-md text-xs xs:text-sm font-medium flex items-center gap-1.5 transition-colors border-t border-b border-r ${
              !isPublic
                ? 'bg-red-50 text-red-700 border-red-200'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
            <Lock className='w-3.5 h-3.5' />
            <span className='whitespace-nowrap'>Private</span>
            {!isPublic && <Check className='w-3.5 h-3.5 ml-1' />}
          </button>
        </div>
      </div>

      {/* Editor area */}
      <div
        data-color-mode='light'
        className={previewMode === 'edit' ? 'block' : 'hidden'}
      >
        <MDEditor
          value={value}
          onChange={handleChange}
          preview='live'
          previewOptions={{
            className: 'markdown-body prose max-w-none',
          }}
          height={400}
          className='border border-gray-200 rounded-md shadow-sm wmde-markdown-var'
        />
      </div>

      {/* Preview area */}
      <div
        className={`bg-white border border-gray-200 rounded-md shadow-sm p-6 markdown-body prose max-w-none overflow-auto h-[400px] ${
          previewMode === 'preview' ? 'block' : 'hidden'
        }`}
        data-color-mode='light'
      >
        <MDPreview source={value} />
      </div>

      {/* Character count and helper tools */}
      <div className='flex justify-between text-sm text-gray-500'>
        <div>Characters: {value.length}</div>
        <button
          type='button'
          onClick={handleCopyToClipboard}
          className='text-blue-600 hover:text-blue-800'
        >
          Copy to clipboard
        </button>
      </div>
    </div>
  );
};
