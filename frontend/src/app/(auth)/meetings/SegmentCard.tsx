'use client';

import React from 'react';
import { Bell } from 'lucide-react';
import { TimingIF, SegmentIF } from '@/interfaces';
import { dotColors, TABLE_TOPICS_SEGMENT_TYPE } from '@/utils/timing';

interface SegmentCardProps {
  segment: SegmentIF;
  isSelected: boolean;
  timing: TimingIF | null;
  onClick: () => void;
  disabled?: boolean;
  isRunning?: boolean;
  isCached?: boolean; // Has unsaved timing in localStorage
}

// Abbreviate segment type for card display
function abbreviateType(type: string): string {
  const abbreviations: Record<string, string> = {
    'Members and Guests Registration, Warm up': 'Warm Up',
    'Meeting Rules Introduction (SAA)': 'SAA',
    'Opening Remarks (President)': 'Opening',
    Timer: 'Timer',
    "Timer's Report": 'Timer Report',
    'Prepared Speech': 'Speech',
    'Table Topics Session': 'TT Session',
    'Table Topics': 'Table Topics',
    Evaluation: 'Evaluation',
    'General Evaluator': 'GE',
    "GE's Report": 'GE Report',
    'Closing Remarks': 'Closing',
    'Award Ceremony': 'Awards',
    Grammarian: 'Grammarian',
    "Grammarian's Report": 'Grammar Rpt',
    'Ah Counter': 'Ah Counter',
    "Ah Counter's Report": 'Ah Rpt',
  };

  if (abbreviations[type]) {
    return abbreviations[type];
  }

  for (const [key, value] of Object.entries(abbreviations)) {
    if (type.includes(key)) {
      return value;
    }
  }

  return type.length > 16 ? type.substring(0, 14) + '...' : type;
}

// Format duration to always have "min" suffix
function formatDurationWithUnit(duration: string): string {
  // If already has "min" or "h", return as-is
  if (duration.includes('min') || duration.includes('h')) {
    return duration;
  }
  // Otherwise, add "min" suffix
  return `${duration}min`;
}

// Format seconds to mm:ss
function formatTimedDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function SegmentCard({
  segment,
  isSelected,
  timing,
  onClick,
  disabled = false,
  isRunning = false,
  isCached = false,
}: SegmentCardProps) {
  const abbreviatedType = abbreviateType(segment.type);
  const roleTaker = segment.role_taker?.name;

  // Determine card styling based on state
  const getCardClasses = () => {
    if (isRunning) {
      return 'border-indigo-500 bg-indigo-50 shadow-md shadow-indigo-200 ring-2 ring-indigo-300 ring-opacity-50 animate-pulse';
    }
    if (isCached) {
      // Unsaved timing - amber background with border
      return isSelected
        ? 'border-amber-500 bg-amber-100 shadow-sm ring-1 ring-amber-400'
        : 'border-amber-400 bg-amber-50 hover:border-amber-500 hover:shadow-sm';
    }
    if (isSelected) {
      return 'border-indigo-400 bg-indigo-50 shadow-sm';
    }
    return 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm';
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        relative flex flex-col items-start text-left
        min-w-[140px] max-w-[160px] p-2.5
        rounded-lg border transition-all
        ${getCardClasses()}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      {/* Top row: time + planned duration + actual (if timed) */}
      <div className='flex items-center justify-between w-full mb-1.5'>
        <span
          className={`text-[10px] font-medium ${
            isSelected ? 'text-indigo-600' : 'text-gray-500'
          }`}
        >
          {segment.start_time}
        </span>
        <div className='flex items-center gap-1'>
          <span
            className={`text-[10px] ${
              isSelected ? 'text-indigo-400' : 'text-gray-400'
            }`}
          >
            {formatDurationWithUnit(segment.duration)}
          </span>
          {/* Hide timing info for Table Topics (multi-speaker session) */}
          {timing && segment.type !== TABLE_TOPICS_SEGMENT_TYPE && (
            <>
              <span
                className={`text-[10px] ${isSelected ? 'text-indigo-300' : 'text-gray-300'}`}
              >
                /
              </span>
              <span
                className={`text-[10px] font-medium ${
                  isSelected ? 'text-indigo-600' : 'text-gray-600'
                }`}
              >
                {formatTimedDuration(timing.actual_duration_seconds)}
              </span>
              {timing.dot_color === 'bell' ? (
                <Bell className='w-2.5 h-2.5 text-red-600 fill-red-600' />
              ) : (
                <div
                  className={`w-2 h-2 rounded-full ${dotColors[timing.dot_color]}`}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Segment type - main label */}
      <span
        className={`text-xs font-medium leading-tight line-clamp-2 ${
          isSelected ? 'text-indigo-700' : 'text-gray-700'
        }`}
      >
        {abbreviatedType}
      </span>

      {/* Role taker */}
      {roleTaker && (
        <span
          className={`text-[10px] mt-1 truncate w-full ${
            isSelected ? 'text-indigo-500' : 'text-gray-400'
          }`}
        >
          {roleTaker}
        </span>
      )}
    </button>
  );
}
