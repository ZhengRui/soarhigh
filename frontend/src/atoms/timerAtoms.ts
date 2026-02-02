import { atom } from 'jotai';

// Cached timing for Table Topics (before batch save)
export interface CachedTiming {
  name: string;
  plannedMinutes: number;
  actualSeconds: number;
  startTime: number;
  endTime: number;
  dotColor: 'gray' | 'green' | 'yellow' | 'red' | 'bell';
}

// Running timer state (single active timer across all segments)
export interface RunningTimerState {
  segmentId: string;
  isRunning: boolean;
  startedAt: number | null;
  speakerName: string; // Used for Table Topics
}

// Cached timings keyed by segment ID
// Persists across component unmounts (subtab/segment switches)
export const cachedTimingsAtom = atom<Record<string, CachedTiming[]>>({});

// Single running timer state - only one timer can run at a time
// Persists the active timer across component unmounts
export const runningTimerAtom = atom<RunningTimerState | null>(null);

// Selected segment ID - persists across subtab switches
export const selectedSegmentIdAtom = atom<string | null>(null);
