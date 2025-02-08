import React, { useEffect, useRef, useState } from 'react';
import { X, Clock, ChevronRight } from 'lucide-react';
import { BaseSegment } from './default';

interface TimePickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialHour: number;
  initialMinute: number;
  initialDuration: number;
  onSave: (hour: number, minute: number, duration: number) => void;
  segmentType: string;
  currentSegmentIndex: number;
  segments: BaseSegment[];
  onBulkSave: (
    startIndex: number,
    endIndex: number,
    hour: number,
    minute: number,
    duration: number
  ) => void;
}

export function TimePickerModal({
  isOpen,
  onClose,
  initialHour,
  initialMinute,
  initialDuration,
  onSave,
  segmentType,
  currentSegmentIndex,
  segments,
  onBulkSave,
}: TimePickerModalProps) {
  const [selectedHour, setSelectedHour] = useState(initialHour);
  const [selectedMinute, setSelectedMinute] = useState(initialMinute);
  const [selectedDuration, setSelectedDuration] = useState(initialDuration);
  const [isBulkMode, setIsBulkMode] = useState(false);
  const [endSegmentIndex, setEndSegmentIndex] = useState<number | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const hourRef = useRef<HTMLDivElement>(null);
  const minuteRef = useRef<HTMLDivElement>(null);
  const durationRef = useRef<HTMLDivElement>(null);

  const hours = Array.from({ length: 24 }, (_, i) => i + 1);
  const minutes = Array.from({ length: 60 }, (_, i) => i);
  const durations = Array.from({ length: 120 }, (_, i) => i + 1);

  const ITEM_HEIGHT = 60;

  useEffect(() => {
    if (isBulkMode) {
      const lastValidIndex = segments.length - 1;
      setEndSegmentIndex(lastValidIndex);
    } else {
      setEndSegmentIndex(null);
    }
  }, [isBulkMode, segments.length]);

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        modalRef.current &&
        !modalRef.current.contains(event.target as Node)
      ) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return;

    const scrollTimeouts: { [key: string]: number } = {};

    const handleScroll = (
      ref: React.RefObject<HTMLDivElement | null>,
      setValue: (value: number) => void,
      values: number[],
      key: string
    ) => {
      if (!ref.current) return;

      // Clear existing timeout for this column
      if (scrollTimeouts[key]) {
        window.clearTimeout(scrollTimeouts[key]);
      }

      const scrollTop = ref.current.scrollTop;
      const index = Math.round(scrollTop / ITEM_HEIGHT);
      const value = values[Math.min(Math.max(index, 0), values.length - 1)];
      setValue(value);

      // Set a new timeout to snap after scrolling stops
      scrollTimeouts[key] = window.setTimeout(() => {
        if (ref.current) {
          ref.current.scrollTo({
            top: index * ITEM_HEIGHT,
            behavior: 'smooth',
          });
        }
      }, 150); // Wait for scroll to finish
    };

    const hourScroll = () =>
      handleScroll(hourRef, setSelectedHour, hours, 'hour');
    const minuteScroll = () =>
      handleScroll(minuteRef, setSelectedMinute, minutes, 'minute');
    const durationScroll = () =>
      handleScroll(durationRef, setSelectedDuration, durations, 'duration');

    // Add scroll event listeners
    hourRef.current?.addEventListener('scroll', hourScroll);
    minuteRef.current?.addEventListener('scroll', minuteScroll);
    durationRef.current?.addEventListener('scroll', durationScroll);

    // Set initial scroll positions
    requestAnimationFrame(() => {
      if (hourRef.current) {
        hourRef.current.scrollTop = hours.indexOf(initialHour) * ITEM_HEIGHT;
      }
      if (minuteRef.current) {
        minuteRef.current.scrollTop =
          minutes.indexOf(initialMinute) * ITEM_HEIGHT;
      }
      if (durationRef.current) {
        durationRef.current.scrollTop =
          durations.indexOf(initialDuration) * ITEM_HEIGHT;
      }
    });

    return () => {
      // Clean up event listeners and timeouts
      hourRef.current?.removeEventListener('scroll', hourScroll);
      minuteRef.current?.removeEventListener('scroll', minuteScroll);
      durationRef.current?.removeEventListener('scroll', durationScroll);
      Object.values(scrollTimeouts).forEach((timeout) =>
        window.clearTimeout(timeout)
      );
    };
  }, [isOpen, initialHour, initialMinute, initialDuration]);

  // Add this new useEffect to manage body scroll
  useEffect(() => {
    if (isOpen) {
      // Disable scrolling on the body when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      // Re-enable scrolling when modal is closed
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    if (isBulkMode && endSegmentIndex !== null && onBulkSave) {
      onBulkSave(
        currentSegmentIndex,
        endSegmentIndex,
        selectedHour,
        selectedMinute,
        selectedDuration
      );
    } else {
      onSave(selectedHour, selectedMinute, selectedDuration);
    }
    onClose();
  };

  const handleSegmentClick = (index: number) => {
    if (index <= currentSegmentIndex) return;
    setEndSegmentIndex(index);
  };

  const renderColumn = (
    numbers: number[],
    ref: React.RefObject<HTMLDivElement | null>,
    unit: string,
    selectedValue: number
  ) => (
    <div className='flex-1 relative -translate-x-4'>
      <div
        ref={ref}
        className='h-[180px] overflow-y-auto scrollbar-hide'
        style={{
          scrollBehavior: 'smooth',
        }}
      >
        <div className='h-[60px]' /> {/* Top padding */}
        {numbers.map((num) => (
          <div
            key={num}
            className={`h-[60px] flex items-center justify-center select-none transition-all duration-200 ${
              num === selectedValue ? 'scale-110' : 'scale-75'
            }`}
          >
            <div
              className={`text-4xl font-medium w-[50px] sm:w-[70px] text-center transition-colors ${
                num === selectedValue ? 'text-gray-900' : 'text-gray-400'
              }`}
            >
              {String(num).padStart(2, '0')}
            </div>
          </div>
        ))}
        <div className='h-[60px]' /> {/* Bottom padding */}
      </div>
      {/* Fixed unit label for the middle (selected) position */}
      <div className='absolute left-0 right-0 top-1/2 -translate-y-1/2 pointer-events-none h-[60px] flex items-center justify-center'>
        <div className='relative w-[50px] sm:w-[70px] text-center'>
          <span className='absolute left-full pl-1 text-sm font-medium text-gray-500'>
            {unit}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <div className='fixed inset-0 bg-black/20 backdrop-blur-sm flex items-center justify-center z-50'>
      <div
        ref={modalRef}
        className='bg-white rounded-xl p-6 w-[calc(100%-2rem)] sm:w-[440px] max-w-[440px] shadow-xl min-w-0'
      >
        <div className='flex justify-between items-start mb-6'>
          <div>
            <h3 className='text-lg font-semibold text-gray-900'>Set Time</h3>
            <p className='text-sm text-gray-500 mt-0.5 line-clamp-1'>
              {segmentType}
            </p>
          </div>
          <button
            onClick={onClose}
            className='p-1.5 rounded-full hover:bg-gray-100 transition-colors'
          >
            <X className='w-5 h-5 text-gray-500' />
          </button>
        </div>

        <div className='relative'>
          {/* Selection indicator */}
          <div className='absolute left-0 right-0 top-1/2 -translate-y-1/2 h-[60px] bg-gradient-to-r from-blue-50 to-purple-50 border-y border-blue-100/50 pointer-events-none' />

          <div className='flex'>
            {renderColumn(hours, hourRef, 'H', selectedHour)}
            <div className='flex items-center z-50 w-6 justify-center -translate-x-2 sm:-translate-x-0'>
              <span className='text-gray-500 text-2xl font-black'>:</span>
            </div>
            {renderColumn(minutes, minuteRef, 'M', selectedMinute)}
            <div className='flex items-center z-50 w-6 justify-center -translate-x-2 sm:-translate-x-0'>
              <span className='text-gray-500 text-2xl font-bold'>+</span>
            </div>
            {renderColumn(durations, durationRef, 'Min', selectedDuration)}
          </div>
        </div>

        {/* Bulk Mode Toggle */}
        <button
          type='button'
          onClick={() => {
            setIsBulkMode(!isBulkMode);
          }}
          className={`mt-6 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-md border transition-all duration-200 ${
            isBulkMode
              ? 'bg-blue-50 border-blue-200 text-blue-700'
              : 'border-gray-200 text-gray-600 hover:bg-gray-50'
          }`}
        >
          <Clock className='w-4 h-4' />
          <span className='text-sm font-medium'>
            {isBulkMode
              ? 'Shift Multiple Segments'
              : 'Enable Multiple Segments Shift'}
          </span>
        </button>

        {/* Timeline Visualization */}
        {isBulkMode && (
          <div className='mt-6 border-t pt-4'>
            <div className='text-sm font-medium text-gray-700 mb-3'>
              Select ending segment:
            </div>
            <div className='space-y-2 max-h-[200px] overflow-y-auto pr-2'>
              {segments.map((segment, index) => {
                const isSelected =
                  index >= currentSegmentIndex &&
                  (endSegmentIndex === null || index <= endSegmentIndex);

                return (
                  <button
                    type='button'
                    key={segment.segment_id}
                    onClick={() => handleSegmentClick(index)}
                    disabled={index <= currentSegmentIndex}
                    className={`w-full text-left p-2 rounded-md transition-all duration-200 ${
                      isSelected
                        ? 'bg-blue-50 border border-blue-200'
                        : 'bg-gray-50 border border-gray-200'
                    } ${
                      index <= currentSegmentIndex
                        ? 'opacity-50 cursor-not-allowed'
                        : 'hover:bg-blue-50'
                    }`}
                  >
                    <div className='flex items-center gap-2'>
                      {isSelected && (
                        <div className='w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0' />
                      )}
                      <span className='text-sm font-medium'>
                        {segment.start_time}
                      </span>
                      <span className='text-xs text-gray-500'>
                        ({segment.duration}min)
                      </span>
                      <ChevronRight
                        className={`w-4 h-4 ${
                          isSelected ? 'text-blue-500' : 'text-gray-400'
                        }`}
                      />
                      <span className='text-sm truncate'>
                        {segment.segment_type}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className='mt-6 flex justify-end gap-3'>
          <button
            onClick={onClose}
            className='px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors'
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className='px-4 py-2 text-sm font-medium bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-md hover:from-blue-700 hover:to-purple-700 transition-colors shadow-sm'
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
