import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

interface TimePickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialHour: number;
  initialMinute: number;
  initialDuration: number;
  onSave: (hour: number, minute: number, duration: number) => void;
  segmentType: string;
}

export function TimePickerModal({
  isOpen,
  onClose,
  initialHour,
  initialMinute,
  initialDuration,
  onSave,
  segmentType,
}: TimePickerModalProps) {
  const [selectedHour, setSelectedHour] = useState(initialHour);
  const [selectedMinute, setSelectedMinute] = useState(initialMinute);
  const [selectedDuration, setSelectedDuration] = useState(initialDuration);

  const modalRef = useRef<HTMLDivElement>(null);
  const hourRef = useRef<HTMLDivElement>(null);
  const minuteRef = useRef<HTMLDivElement>(null);
  const durationRef = useRef<HTMLDivElement>(null);

  const hours = Array.from({ length: 24 }, (_, i) => i + 1);
  const minutes = Array.from({ length: 60 }, (_, i) => i);
  const durations = Array.from({ length: 120 }, (_, i) => i + 1);

  const ITEM_HEIGHT = 60;

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

  if (!isOpen) return null;

  const handleSave = () => {
    onSave(selectedHour, selectedMinute, selectedDuration);
    onClose();
  };

  const renderColumn = (
    numbers: number[],
    ref: React.RefObject<HTMLDivElement | null>,
    unit: string,
    selectedValue: number
  ) => (
    <div className='flex-1 relative'>
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
              num === selectedValue ? 'scale-110' : 'scale-100'
            }`}
          >
            <div
              className={`text-4xl font-medium w-[70px] text-center transition-colors ${
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
        <div className='relative w-[70px] text-center'>
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
        className='bg-white rounded-xl p-6 w-[440px] shadow-xl'
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

          <div className='flex gap-8'>
            {renderColumn(hours, hourRef, 'H', selectedHour)}
            {renderColumn(minutes, minuteRef, 'M', selectedMinute)}
            {renderColumn(durations, durationRef, 'Min', selectedDuration)}
          </div>
        </div>

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
