'use client';

import { useState } from 'react';
import { Brain, ChevronDown, ChevronRight } from 'lucide-react';

export function ThinkingBlock({
  content,
  streaming,
}: {
  content: string;
  streaming: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className='mb-1.5 border border-gray-200 rounded-md bg-gray-50/60'>
      <button
        type='button'
        onClick={() => setExpanded((v) => !v)}
        className='flex items-center gap-1.5 w-full px-2 py-1 text-[11px] font-mono text-gray-500 hover:text-gray-700 transition-colors'
      >
        {expanded ? (
          <ChevronDown className='w-3 h-3' />
        ) : (
          <ChevronRight className='w-3 h-3' />
        )}
        <Brain className='w-3 h-3' />
        <span className='font-semibold'>
          {streaming ? 'Thinking…' : 'Thought'}
        </span>
        {!expanded && (
          <span className='opacity-60 truncate text-left flex-1'>
            {content.slice(0, 80)}
            {content.length > 80 ? '…' : ''}
          </span>
        )}
      </button>
      {expanded && (
        <div className='px-2 pb-2 pt-0 text-[11px] font-mono text-gray-600 whitespace-pre-wrap break-words leading-relaxed'>
          {content}
        </div>
      )}
    </div>
  );
}
