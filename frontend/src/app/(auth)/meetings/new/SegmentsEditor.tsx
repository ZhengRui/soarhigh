import React, { useState, useRef, useEffect } from 'react';
import { Users, X, Plus, ChevronDown } from 'lucide-react';
import {
  BaseSegment,
  DEFAULT_SEGMENTS_REGULAR_MEETING,
  SEGMENT_TYPE_MAP,
} from './default';

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
  const [openDropdownIndex, setOpenDropdownIndex] = useState<number | null>(
    null
  );
  const dropdownRef = useRef<HTMLDivElement>(null);
  const segmentTypeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (segmentTypeRef.current?.contains(event.target as Node)) {
        return;
      }

      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setOpenDropdownIndex(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

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
  const hoveredClasses =
    'group-hover:-translate-y-1 transition-all duration-300 ease-out';
  const deletingClassesFunction = (index: number) => {
    return deletingSegments.includes(index)
      ? 'opacity-0 group-hover:opacity-0'
      : 'opacity-100';
  };

  return (
    <div className='space-y-4'>
      {segments.map((segment, index) => (
        <div
          key={segment.segment_id}
          className='group relative flex gap-4 items-start py-4 px-2 sm:px-4 rounded-lg'
        >
          <div
            className={`absolute inset-0 w-full h-full rounded-lg
              group-hover:shadow-[0_8px_16px_-6px_rgba(0,0,0,0.05),0_4px_8px_-4px_rgba(59,130,246,0.1)]
             ${hoveredClasses}
             ${deletingClassesFunction(index)}`}
          />

          {/* Delete Button */}
          {onSegmentDelete && (
            <button
              type='button'
              onClick={() => handleDelete(index)}
              className={`absolute -top-2 -right-2 p-1.5 rounded-full bg-white shadow-md opacity-0 group-hover:-translate-y-1 group-hover:opacity-100 transform scale-75 group-hover:scale-100 transition-all duration-200 hover:bg-red-50 z-20
                ${deletingSegments.includes(index) ? 'opacity-0 group-hover:opacity-0' : ''}`}
              title='Delete segment'
              disabled={deletingSegments.includes(index)}
            >
              <X className='w-4 h-4 text-gray-400 hover:text-red-500 transition-colors' />
            </button>
          )}

          <div
            className={`w-16 sm:w-24 flex-shrink-0 flex flex-col items-start pt-1.5
              ${hoveredClasses}
              ${deletingClassesFunction(index)}`}
          >
            <span className='text-sm font-medium text-indigo-600'>
              {segment.start_time}
            </span>
            <span className='text-xs text-gray-500'>{segment.duration}min</span>
          </div>

          <div className='flex-grow space-y-2'>
            <div className='relative select-none'>
              <div
                ref={openDropdownIndex === index ? segmentTypeRef : null}
                className={`flex items-center gap-1 cursor-pointer
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
                onClick={() => {
                  setOpenDropdownIndex(
                    openDropdownIndex === index ? null : index
                  );
                }}
              >
                <span className='text-sm font-medium text-gray-900'>
                  {segment.segment_type}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
                    openDropdownIndex === index ? 'transform rotate-180' : ''
                  }`}
                />
              </div>
              {openDropdownIndex === index && (
                <div
                  ref={dropdownRef}
                  className={`absolute left-0 top-full mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-20
                    ${hoveredClasses}
                    ${deletingClassesFunction(index)}`}
                >
                  <div className='py-1 max-h-80 overflow-auto'>
                    {Object.keys(SEGMENT_TYPE_MAP).map((type) => (
                      <div
                        key={type}
                        className='px-4 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                      >
                        {type}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {segment.role_taker.editable && (
              <div
                className={`relative
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
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
              <div
                className={`relative
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
                <input
                  type='text'
                  value=''
                  onChange={(e) =>
                    onSegmentChange(index, 'title', e.target.value)
                  }
                  placeholder={segment.title.placeholder}
                  className={inputClasses}
                />
              </div>
            )}

            {segment.content.editable && (
              <div
                className={`relative
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
                <input
                  type='text'
                  value=''
                  onChange={(e) =>
                    onSegmentChange(index, 'content', e.target.value)
                  }
                  placeholder={segment.content.placeholder}
                  className={inputClasses}
                />
              </div>
            )}
          </div>

          {/* Thinner decorative gradient line */}
          <div
            className={`absolute left-16 sm:left-24 top-0 bottom-0 w-[1px] bg-gradient-to-b from-indigo-600/10 to-purple-600/10
              ${hoveredClasses}
              ${deletingClassesFunction(index)}`}
          />

          {/* Add Button */}
          {onSegmentAdd && (
            <button
              type='button'
              onClick={() => onSegmentAdd(index)}
              className={`absolute -bottom-3.5 -translate-x-3.5 left-16 sm:left-24 p-1.5 rounded-full bg-white shadow-md opacity-0 group-hover:-translate-y-1 group-hover:opacity-100 transform scale-75 group-hover:scale-100 transition-all duration-200 hover:bg-indigo-50 z-20
                ${deletingSegments.includes(index) ? 'opacity-0 group-hover:opacity-0' : ''}`}
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
