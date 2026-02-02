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

interface SegmentCardProps {
  segment: SegmentIF;
  isSelected: boolean;
  timing: TimingIF | null;
  allTimings?: TimingIF[]; // All timings for Table Topics (multiple speakers)
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
  allTimings = [],
  onClick,
  disabled = false,
  isRunning = false,
  isCached = false,
}: SegmentCardProps) {
  const abbreviatedType = abbreviateType(segment.type);
  const roleTaker = segment.role_taker?.name;
  const isTableTopics = segment.type === TABLE_TOPICS_SEGMENT_TYPE;

  // Popover state for Table Topics speakers
  const [showSpeakers, setShowSpeakers] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Handle opening popover - calculate position immediately
  const handleToggleSpeakers = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (allTimings.length === 0) return;

    if (!showSpeakers && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPopoverPosition({
        top: rect.bottom + 4,
        left: rect.left,
      });
    }
    setShowSpeakers(!showSpeakers);
  };

  // Close popover when clicking outside or scrolling
  useEffect(() => {
    if (!showSpeakers) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setShowSpeakers(false);
      }
    };

    const handleScroll = () => {
      setShowSpeakers(false);
    };

    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('scroll', handleScroll, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', handleScroll, true);
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

      {/* Role taker or Table Topics speakers icon */}
      {isTableTopics ? (
        <div className='mt-1'>
          <button
            ref={triggerRef}
            onClick={handleToggleSpeakers}
            className={`flex items-center gap-1 text-[10px] ${
              allTimings.length > 0
                ? isSelected
                  ? 'text-indigo-500 hover:text-indigo-600'
                  : 'text-gray-400 hover:text-gray-600'
                : isSelected
                  ? 'text-indigo-300'
                  : 'text-gray-300'
            } transition-colors`}
            disabled={allTimings.length === 0}
          >
            <Users className='w-3 h-3' />
            <span>
              {allTimings.length} speaker{allTimings.length !== 1 ? 's' : ''}
            </span>
          </button>

          {/* Speakers Popover - rendered via portal to avoid clipping */}
          {showSpeakers &&
            allTimings.length > 0 &&
            typeof window !== 'undefined' &&
            createPortal(
              <div
                ref={popoverRef}
                className='fixed z-[9999] bg-white border border-gray-200 rounded-lg shadow-lg p-2 min-w-[160px] max-w-[200px]'
                style={{
                  top: popoverPosition.top,
                  left: popoverPosition.left,
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div className='text-[10px] font-medium text-gray-500 mb-1.5 px-1'>
                  Speakers ({allTimings.length})
                </div>
                <div className='space-y-1 max-h-[150px] overflow-y-auto'>
                  {allTimings.map((t, idx) => (
                    <div
                      key={t.id || idx}
                      className='flex items-center justify-between gap-2 px-1 py-0.5 rounded hover:bg-gray-50'
                    >
                      <div className='flex items-center gap-1.5 min-w-0'>
                        {t.dot_color === 'bell' ? (
                          <Bell className='w-2.5 h-2.5 text-red-600 fill-red-600 flex-shrink-0' />
                        ) : (
                          <div
                            className={`w-2 h-2 rounded-full flex-shrink-0 ${dotColors[t.dot_color]}`}
                          />
                        )}
                        <span className='text-[10px] text-gray-700 truncate'>
                          {t.name || 'Speaker'}
                        </span>
                      </div>
                      <span className='text-[10px] font-mono text-gray-500 flex-shrink-0'>
                        {formatDuration(t.actual_duration_seconds)}
                      </span>
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
