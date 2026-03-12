'use client';

import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Bell, Users } from 'lucide-react';
import { TimingIF, SegmentIF } from '@/interfaces';
import {
  dotColors,
  TABLE_TOPICS_SEGMENT_TYPE,
  formatDuration,
} from '@/utils/timing';

export interface SpeakerTimingEntry {
  id?: string;
  name?: string | null;
  dotColor: TimingIF['dot_color'];
  actualDurationSeconds: number;
  plannedDurationMinutes: number;
  actualStartTime?: string;
  actualEndTime?: string;
  isCached?: boolean;
}

const speakerStatusOrder: Record<TimingIF['dot_color'], number> = {
  gray: 0,
  green: 1,
  yellow: 2,
  red: 3,
  bell: 4,
};

interface SegmentCardProps {
  segment: SegmentIF;
  isSelected: boolean;
  timing: TimingIF | null;
  speakerEntries?: SpeakerTimingEntry[];
  cachedTiming?: {
    dotColor: TimingIF['dot_color'];
    actualDurationSeconds: number;
  } | null;
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
  speakerEntries = [],
  cachedTiming = null,
  onClick,
  disabled = false,
  isRunning = false,
  isCached = false,
}: SegmentCardProps) {
  const abbreviatedType = abbreviateType(segment.type);
  const roleTaker = segment.role_taker?.name;
  const isTableTopics = segment.type === TABLE_TOPICS_SEGMENT_TYPE;
  const displayTiming =
    timing ||
    (cachedTiming
      ? {
          actual_duration_seconds: cachedTiming.actualDurationSeconds,
          dot_color: cachedTiming.dotColor,
        }
      : null);
  const sortedSpeakerEntries = [...speakerEntries].sort((a, b) => {
    const statusDiff =
      speakerStatusOrder[a.dotColor] - speakerStatusOrder[b.dotColor];
    if (statusDiff !== 0) {
      return statusDiff;
    }

    const aDistance = a.actualDurationSeconds - a.plannedDurationMinutes * 60;
    const bDistance = b.actualDurationSeconds - b.plannedDurationMinutes * 60;
    return aDistance - bDistance;
  });

  // Popover state for Table Topics speakers
  const [showSpeakers, setShowSpeakers] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Handle opening popover - calculate position immediately
  const handleToggleSpeakers = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (sortedSpeakerEntries.length === 0) return;

    if (!showSpeakers && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPopoverPosition({
        top: rect.bottom + 4,
        left: rect.left,
      });
    }
    setShowSpeakers(!showSpeakers);
  };

  // Close popover when clicking outside or when an outside container scrolls.
  useEffect(() => {
    if (!showSpeakers) return;

    const isWithinPopover = (target: EventTarget | null) => {
      if (!(target instanceof Node)) {
        return false;
      }

      return Boolean(
        popoverRef.current?.contains(target) ||
          triggerRef.current?.contains(target)
      );
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (!isWithinPopover(e.target)) {
        setShowSpeakers(false);
      }
    };

    const handleScrollOutside = (e: Event) => {
      if (!isWithinPopover(e.target)) {
        setShowSpeakers(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('scroll', handleScrollOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('scroll', handleScrollOutside, true);
    };
  }, [showSpeakers]);

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
    <div
      role='button'
      tabIndex={disabled ? -1 : 0}
      onClick={disabled ? undefined : onClick}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
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
          {displayTiming && segment.type !== TABLE_TOPICS_SEGMENT_TYPE && (
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
                {formatTimedDuration(displayTiming.actual_duration_seconds)}
              </span>
              {displayTiming.dot_color === 'bell' ? (
                <Bell className='w-2.5 h-2.5 text-red-600 fill-red-600' />
              ) : (
                <div
                  className={`w-2 h-2 rounded-full ${dotColors[displayTiming.dot_color]}`}
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

      {/* Role taker or Table Topics speakers icon */}
      {isTableTopics ? (
        <div className='mt-1'>
          <button
            ref={triggerRef}
            onClick={handleToggleSpeakers}
            className={`flex items-center gap-1 text-[10px] ${
              sortedSpeakerEntries.length > 0
                ? isSelected
                  ? 'text-indigo-500 hover:text-indigo-600'
                  : 'text-gray-400 hover:text-gray-600'
                : isSelected
                  ? 'text-indigo-300'
                  : 'text-gray-300'
            } transition-colors`}
            disabled={sortedSpeakerEntries.length === 0}
          >
            <Users className='w-3 h-3' />
            <span>
              {sortedSpeakerEntries.length} speaker
              {sortedSpeakerEntries.length !== 1 ? 's' : ''}
            </span>
          </button>

          {/* Speakers Popover - rendered via portal to avoid clipping */}
          {showSpeakers &&
            sortedSpeakerEntries.length > 0 &&
            typeof window !== 'undefined' &&
            createPortal(
              <div
                ref={popoverRef}
                className='fixed z-[9999] bg-white border border-gray-200 rounded-xl shadow-lg p-3 w-[240px] max-w-[260px]'
                style={{
                  top: popoverPosition.top,
                  left: popoverPosition.left,
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div className='text-[10px] font-medium text-gray-500 mb-2 px-1'>
                  Speakers ({sortedSpeakerEntries.length})
                </div>
                <div className='space-y-3 max-h-[24vh] overflow-y-auto pr-1 overscroll-contain'>
                  {sortedSpeakerEntries.map((entry, idx) => (
                    <div key={entry.id || idx} className='px-1'>
                      <div className='flex items-center gap-1.5 mb-1 min-w-0'>
                        {entry.dotColor === 'bell' ? (
                          <Bell className='w-2.5 h-2.5 text-red-600 fill-red-600 flex-shrink-0' />
                        ) : (
                          <div
                            className={`w-2 h-2 rounded-full flex-shrink-0 ${dotColors[entry.dotColor]}`}
                          />
                        )}
                        <span className='text-[10px] text-gray-700 truncate'>
                          {entry.name || 'Speaker'}
                        </span>
                      </div>
                      <div className='pl-4 text-[10px] font-mono text-gray-500 whitespace-nowrap'>
                        {entry.actualStartTime && entry.actualEndTime
                          ? `${entry.actualStartTime} - ${entry.actualEndTime} (${formatDuration(entry.actualDurationSeconds)}${entry.isCached ? ', unsaved' : ''})`
                          : `${formatDuration(entry.actualDurationSeconds)}${entry.isCached ? ' (unsaved)' : ''}`}
                      </div>
                    </div>
                  ))}
                </div>
              </div>,
              document.body
            )}
        </div>
      ) : (
        roleTaker && (
          <span
            className={`text-[10px] mt-1 truncate w-full ${
              isSelected ? 'text-indigo-500' : 'text-gray-400'
            }`}
          >
            {roleTaker}
          </span>
        )
      )}
    </div>
  );
}
