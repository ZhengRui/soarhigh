import React, { useState } from 'react';
import { Users, X, Plus } from 'lucide-react';
import { BaseSegment, DEFAULT_SEGMENTS_REGULAR_MEETING } from './default';

interface SegmentsEditorProps {
  segments: BaseSegment[];
  onSegmentChange: (
    index: number,
    field: keyof BaseSegment,
    value: string
  ) => void;
  onSegmentDelete?: (index: number) => void;
  onSegmentAdd?: (index: number) => void;
}

export function SegmentsEditor({
  segments = DEFAULT_SEGMENTS_REGULAR_MEETING,
  onSegmentChange,
  onSegmentDelete,
  onSegmentAdd,
}: SegmentsEditorProps) {
  const [deletingSegments, setDeletingSegments] = useState<number[]>([]);

  const handleDelete = (index: number) => {
    setDeletingSegments((prev) => [...prev, index]);
    setTimeout(() => {
      onSegmentDelete?.(index);
      setDeletingSegments((prev) => prev.filter((i) => i !== index));
    }, 300);
  };

  const inputClasses =
    'block w-full px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-[0.5px] focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';
  const inputWithIconClasses =
    'block w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-[0.5px] focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';

  return (
    <div className='space-y-4'>
      {segments.map((segment, index) => (
        <div
          key={segment.segment_id}
          className={`group relative flex gap-4 items-start py-4 px-2 sm:px-4 rounded-lg
            transition-all duration-300 ease-out
            hover:-translate-y-1 hover:shadow-[0_8px_16px_-6px_rgba(0,0,0,0.05),0_4px_8px_-4px_rgba(59,130,246,0.1)]
            ${deletingSegments.includes(index) ? 'opacity-0 -translate-y-4' : 'opacity-100 translate-y-0'}`}
        >
          {/* Delete Button */}
          {onSegmentDelete && (
            <button
              type='button'
              onClick={() => handleDelete(index)}
              className='absolute -top-2 -right-2 p-1.5 rounded-full bg-white shadow-md opacity-0 group-hover:opacity-100 transform scale-75 group-hover:scale-100 transition-all duration-200 hover:bg-red-50 z-20'
              title='Delete segment'
              disabled={deletingSegments.includes(index)}
            >
              <X className='w-4 h-4 text-gray-400 hover:text-red-500 transition-colors' />
            </button>
          )}

          <div className='w-16 sm:w-24 flex-shrink-0 flex flex-col items-start pt-1.5'>
            <span className='text-sm font-medium text-indigo-600'>
              {segment.start_time}
            </span>
            <span className='text-xs text-gray-500'>{segment.duration}min</span>
          </div>

          <div className='flex-grow space-y-2'>
            <div className='text-sm font-medium text-gray-900'>
              {segment.segment_type}
            </div>

            {segment.role_taker.editable && (
              <div className='relative'>
                <input
                  type='text'
                  value=''
                  onChange={(e) =>
                    onSegmentChange(index, 'role_taker', e.target.value)
                  }
                  placeholder={segment.role_taker.placeholder}
                  className={inputWithIconClasses}
                />
                <Users className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
              </div>
            )}

            {segment.title.editable && (
              <input
                type='text'
                value=''
                onChange={(e) =>
                  onSegmentChange(index, 'title', e.target.value)
                }
                placeholder={segment.title.placeholder}
                className={inputClasses}
              />
            )}

            {segment.content.editable && (
              <input
                type='text'
                value=''
                onChange={(e) =>
                  onSegmentChange(index, 'content', e.target.value)
                }
                placeholder={segment.content.placeholder}
                className={inputClasses}
              />
            )}
          </div>

          {/* Thinner decorative gradient line */}
          <div className='absolute left-16 sm:left-24 top-0 bottom-0 w-[1px] bg-gradient-to-b from-indigo-600/10 to-purple-600/10' />

          {/* Add Button */}
          {onSegmentAdd && (
            <button
              type='button'
              onClick={() => onSegmentAdd(index)}
              className='absolute -bottom-3.5 -translate-x-3.5 left-16 sm:left-24 p-1.5 rounded-full bg-white shadow-md opacity-0 group-hover:opacity-100 transform scale-75 group-hover:scale-100 transition-all duration-200 hover:bg-indigo-50 z-20'
              title='Add segment below'
            >
              <Plus className='w-4 h-4 text-gray-400 hover:text-indigo-500 transition-colors' />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
