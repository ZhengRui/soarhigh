'use client';

import React from 'react';
import { Bell } from 'lucide-react';
import {
  getCardTimes,
  getCountdownZone,
  formatDuration,
  timerTextColors,
} from '@/utils/timing';

interface CardSignalsProps {
  plannedMinutes: number;
}

/**
 * Displays the green/yellow/red card signal times for a timer
 */
export function CardSignals({ plannedMinutes }: CardSignalsProps) {
  const cards = getCardTimes(plannedMinutes);

  return (
    <div className='flex items-center justify-center sm:justify-end gap-3 text-xs'>
      <span className='text-green-600 font-mono'>
        <span className='inline-block w-2 h-2 bg-green-500 rounded-full mr-1'></span>
        <span className='inline-block w-10 text-left'>
          {formatDuration(cards.green)}
        </span>
      </span>
      <span className='text-yellow-600 font-mono'>
        <span className='inline-block w-2 h-2 bg-yellow-500 rounded-full mr-1'></span>
        <span className='inline-block w-10 text-left'>
          {formatDuration(cards.yellow)}
        </span>
      </span>
      <span className='text-red-600 font-mono'>
        <span className='inline-block w-2 h-2 bg-red-500 rounded-full mr-1'></span>
        <span className='inline-block w-10 text-left'>
          {formatDuration(cards.red)}
        </span>
      </span>
    </div>
  );
}

interface TimerDisplayProps {
  elapsed: number;
  plannedMinutes: number;
  isRunning: boolean;
}

/**
 * Displays the main timer countdown with color zones and overtime bell
 */
export function TimerDisplay({
  elapsed,
  plannedMinutes,
  isRunning,
}: TimerDisplayProps) {
  const zone = getCountdownZone(plannedMinutes, elapsed);
  const cards = getCardTimes(plannedMinutes);
  const remaining = Math.max(0, cards.red - elapsed);

  return (
    <div className='text-center py-6 sm:py-4'>
      <div className='relative inline-flex items-center justify-center'>
        <span
          className={`text-5xl sm:text-6xl font-mono font-bold tracking-tight transition-colors tabular-nums ${
            isRunning ? timerTextColors[zone] : 'text-gray-300'
          }`}
        >
          {formatDuration(elapsed)}
        </span>
        {/* Bell icon when 30+ seconds over */}
        {isRunning && zone === 'overtime' && (
          <Bell className='absolute -right-10 sm:-right-12 w-8 h-8 sm:w-10 sm:h-10 text-red-600 fill-red-600 animate-pulse' />
        )}
      </div>
      {/* Time hint - always reserve height */}
      <p className='text-xs text-gray-400 mt-2 h-4 tabular-nums'>
        {isRunning &&
          (elapsed >= cards.red
            ? `${formatDuration(elapsed - cards.red)} over`
            : `${formatDuration(remaining)} remaining`)}
      </p>
    </div>
  );
}
