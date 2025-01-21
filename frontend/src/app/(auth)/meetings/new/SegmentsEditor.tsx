import React, { useState, useRef, useEffect } from 'react';
import { Users, X, Plus, ChevronDown, Link, Hash } from 'lucide-react';
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

  const [openTypeDropdownIndex, setOpenTypeDropdownIndex] = useState<
    number | null
  >(null);
  const typeDropdownRef = useRef<HTMLDivElement>(null);
  const segmentTypeRef = useRef<HTMLDivElement>(null);

  const [openRelatedDropdownIndex, setOpenRelatedDropdownIndex] = useState<
    number | null
  >(null);
  const relatedDropdownRef = useRef<HTMLDivElement>(null);
  const relatedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutsideOfTypeDropdown(event: MouseEvent) {
      if (segmentTypeRef.current?.contains(event.target as Node)) {
        return;
      }

      if (
        typeDropdownRef.current &&
        !typeDropdownRef.current.contains(event.target as Node)
      ) {
        setOpenTypeDropdownIndex(null);
      }
    }

    function handleClickOutsideOfRelatedDropdown(event: MouseEvent) {
      if (relatedRef.current?.contains(event.target as Node)) {
        return;
      }

      if (
        relatedDropdownRef.current &&
        !relatedDropdownRef.current.contains(event.target as Node)
      ) {
        setOpenRelatedDropdownIndex(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutsideOfTypeDropdown);
    document.addEventListener('mousedown', handleClickOutsideOfRelatedDropdown);

    return () => {
      document.removeEventListener(
        'mousedown',
        handleClickOutsideOfTypeDropdown
      );
      document.removeEventListener(
        'mousedown',
        handleClickOutsideOfRelatedDropdown
      );
    };
  }, []);

  const handleDelete = (index: number) => {
    setDeletingSegments((prev) => [...prev, index]);
    setTimeout(() => {
      onSegmentDelete?.(index);
      setDeletingSegments((prev) => prev.filter((i) => i !== index));
    }, 300);
  };

  const handleSegmentTypeChange = (index: number, newType: string) => {
    onSegmentChange(index, 'segment_type', newType);
    setOpenTypeDropdownIndex(null);
  };

  const handleAddRelatedSegment = (index: number, relatedSegmentId: string) => {
    const segment = segments[index];
    const newRelatedIds = segment.related_segment_ids
      ? `${segment.related_segment_ids},${relatedSegmentId}`
      : relatedSegmentId;

    onSegmentChange(index, 'related_segment_ids', newRelatedIds);
    setOpenRelatedDropdownIndex(null);
  };

  const handleRemoveRelatedSegment = (
    index: number,
    relatedSegmentId: string
  ) => {
    const segment = segments[index];
    const newRelatedIds = segment.related_segment_ids
      .split(',')
      .filter((id) => id !== relatedSegmentId)
      .join(',');

    onSegmentChange(index, 'related_segment_ids', newRelatedIds);
  };

  const inputClasses =
    'block w-full px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';
  const inputWithIconClasses =
    'block w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';
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
          className='group relative flex flex-col sm:flex-row gap-4 items-start py-4 px-2 sm:px-4 rounded-lg'
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
            className={`w-full sm:w-24 flex-shrink-0 flex sm:flex-col items-center sm:items-start justify-between
              ${hoveredClasses}
              ${deletingClassesFunction(index)}`}
          >
            <div className='flex sm:flex-col items-center sm:items-start gap-2 sm:gap-0'>
              <span className='text-sm font-medium text-indigo-600'>
                {segment.start_time}
              </span>
              <span className='text-xs text-gray-500'>
                {segment.duration}min
              </span>
            </div>
            <div className='text-[10px] text-gray-400 sm:pt-1 font-mono flex items-center gap-0.5'>
              <Hash className='w-2 h-2' />
              <span>{segment.segment_id.slice(0, 5)}</span>
            </div>
          </div>

          <div className='flex-grow space-y-2 w-full'>
            <div className='relative select-none'>
              <div
                ref={openTypeDropdownIndex === index ? segmentTypeRef : null}
                className={`flex items-center gap-1 cursor-pointer
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
                onClick={() => {
                  setOpenTypeDropdownIndex(
                    openTypeDropdownIndex === index ? null : index
                  );
                }}
              >
                <span className='text-sm font-medium text-gray-900'>
                  {segment.segment_type}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
                    openTypeDropdownIndex === index
                      ? 'transform rotate-180'
                      : ''
                  }`}
                />
              </div>
              {openTypeDropdownIndex === index && (
                <div
                  ref={typeDropdownRef}
                  className={`absolute left-0 top-full mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30
                    ${hoveredClasses}
                    ${deletingClassesFunction(index)}`}
                >
                  <div className='py-1 max-h-80 overflow-auto'>
                    {Object.keys(SEGMENT_TYPE_MAP).map((type) => (
                      <div
                        key={type}
                        className='px-4 py-2 text-xs text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                        onClick={() => handleSegmentTypeChange(index, type)}
                      >
                        {type}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {segment.role_taker_config.editable && (
              <div
                className={`relative
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
                <input
                  type='text'
                  value={segment.role_taker}
                  onChange={(e) =>
                    onSegmentChange(index, 'role_taker', e.target.value)
                  }
                  placeholder={segment.role_taker_config.placeholder}
                  className={inputWithIconClasses}
                />
                <Users className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
              </div>
            )}

            {segment.title_config.editable && (
              <div
                className={`relative
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
                <input
                  type='text'
                  value={segment.title}
                  onChange={(e) =>
                    onSegmentChange(index, 'title', e.target.value)
                  }
                  placeholder={segment.title_config.placeholder}
                  className={inputClasses}
                />
              </div>
            )}

            {segment.content_config.editable && (
              <div
                className={`relative
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
                <input
                  type='text'
                  value={segment.content}
                  onChange={(e) =>
                    onSegmentChange(index, 'content', e.target.value)
                  }
                  placeholder={segment.content_config.placeholder}
                  className={inputClasses}
                />
              </div>
            )}

            {/* Existing Related Segments Tags */}
            {segment.related_segment_ids && (
              <div
                className={`flex flex-wrap gap-2
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
              >
                {segment.related_segment_ids
                  .split(',')
                  .map((segment_id) => {
                    const relatedSegment = segments.find(
                      (s) => s.segment_id === segment_id
                    );
                    return (
                      relatedSegment && (
                        <div
                          key={segment_id}
                          className='inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-700 border border-indigo-100 shadow-sm group/tag hover:shadow-md transition-all duration-200'
                          title={`# ${segment_id.slice(0, 5)}`}
                        >
                          <Link className='w-3.5 h-3.5 mr-1.5 text-indigo-500 flex-shrink-0' />
                          <span className='font-semibold truncate max-w-40'>
                            {relatedSegment.segment_type}
                          </span>
                          <button
                            onClick={() =>
                              handleRemoveRelatedSegment(index, segment_id)
                            }
                            className='ml-1.5 p-0.5 rounded-full hover:bg-indigo-100 opacity-0 group-hover/tag:opacity-100 transition-opacity flex-shrink-0'
                          >
                            <X className='w-3 h-3 text-indigo-500' />
                          </button>
                        </div>
                      )
                    );
                  })
                  .filter(Boolean)}
              </div>
            )}

            {/* Add Related Segment Dropdown */}

            {segment.related_segment_ids_config.editable && (
              <div className='relative w-full sm:w-auto select-none'>
                <div
                  ref={openRelatedDropdownIndex === index ? relatedRef : null}
                  className={`flex max-w-44 items-center gap-1 px-2 py-1 text-xs rounded-md border border-gray-300 bg-white text-gray-700 cursor-pointer hover:border-indigo-300
                  ${hoveredClasses}
                  ${deletingClassesFunction(index)}`}
                  onClick={() =>
                    setOpenRelatedDropdownIndex(
                      openRelatedDropdownIndex === index ? null : index
                    )
                  }
                >
                  <Plus className='w-4 h-4 text-gray-400' />
                  <span>Add related segment...</span>
                </div>

                {openRelatedDropdownIndex === index && (
                  <div
                    ref={relatedDropdownRef}
                    className={`absolute left-0 top-full mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30
                    ${hoveredClasses}
                    ${deletingClassesFunction(index)}`}
                  >
                    <div className='py-1 max-h-60 overflow-auto'>
                      {(() => {
                        // Create Set once for O(1) lookups
                        const relatedIds = new Set(
                          segment.related_segment_ids?.split(',') || []
                        );

                        return segments
                          .filter(
                            (s) =>
                              s.segment_id !== segment.segment_id &&
                              !relatedIds.has(s.segment_id)
                          )
                          .map((s) => (
                            <div
                              key={s.segment_id}
                              className='px-4 py-2 text-xs text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                              onClick={() =>
                                handleAddRelatedSegment(index, s.segment_id)
                              }
                            >
                              {`${s.segment_type} (# ${s.segment_id.slice(0, 5)})`}
                            </div>
                          ));
                      })()}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Thinner decorative gradient line */}
          <div
            className={`hidden sm:block absolute left-16 sm:left-24 top-0 bottom-0 w-[1px] bg-gradient-to-b from-indigo-600/10 to-purple-600/10
              ${hoveredClasses}
              ${deletingClassesFunction(index)}`}
          />

          {/* Add Button */}
          {onSegmentAdd && (
            <button
              type='button'
              onClick={() => onSegmentAdd(index)}
              className={`absolute -bottom-3.5 -translate-x-3.5 left-full sm:left-24 p-1.5 rounded-full bg-white shadow-md opacity-0 group-hover:-translate-y-1 group-hover:opacity-100 transform scale-75 group-hover:scale-100 transition-all duration-200 hover:bg-indigo-50 z-20
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
