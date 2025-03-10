'use client';

import React from 'react';
import dynamic from 'next/dynamic';

// Dynamically import the markdown preview component
const MDPreview = dynamic(
  () => import('@uiw/react-md-editor').then((mod) => mod.default.Markdown),
  {
    ssr: false,
    loading: () => (
      <div className='h-[200px] w-full bg-gray-100 rounded-md animate-pulse flex items-center justify-center'>
        <p className='text-gray-500'>Loading content...</p>
      </div>
    ),
  }
);

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
}) => {
  return (
    <div
      className={`prose max-w-none markdown-body ${className}`}
      data-color-mode='light'
    >
      <MDPreview source={content} />
    </div>
  );
};
