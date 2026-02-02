/**
 * localStorage utility for caching timing data.
 *
 * Provides persistence for unsaved timing records across page refreshes.
 * Each meeting has its own storage key to prevent interference.
 */

// Storage key pattern: `timing_cache_{meetingId}`
const STORAGE_KEY_PREFIX = 'timing_cache_';

// Session storage key for running timer
const RUNNING_TIMER_KEY = 'running_timer';

// Cache TTL: 24 hours in milliseconds
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export type DotColor = 'gray' | 'green' | 'yellow' | 'red' | 'bell';

export interface CachedTimingEntry {
  name: string | null;
  plannedDurationMinutes: number;
  startedAt: number; // timestamp ms
  endedAt: number; // timestamp ms
  dotColor: DotColor;
}

export interface CachedSegmentTiming {
  segmentId: string;
  segmentType: string;
  entries: CachedTimingEntry[];
}

// Keyed by segment_id
export type CachedTimingsState = Record<string, CachedSegmentTiming>;

// Storage format with timestamp for TTL cleanup
interface StoredCacheData {
  cachedAt: number; // timestamp ms when cache was last updated
  timings: CachedTimingsState;
}

// Running timer state (persisted to sessionStorage)
export interface RunningTimerState {
  meetingId: string;
  segmentId: string;
  isRunning: boolean;
  startedAt: number | null;
  speakerName: string; // Used for Table Topics
}

function getStorageKey(meetingId: string): string {
  return `${STORAGE_KEY_PREFIX}${meetingId}`;
}

/**
 * Load cached timings from localStorage for a meeting.
 * Returns empty object if cache is expired (older than 24 hours).
 */
export function loadCachedTimings(meetingId: string): CachedTimingsState {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(getStorageKey(meetingId));
    if (!raw) return {};

    const parsed = JSON.parse(raw);

    // Handle new format with timestamp
    if (parsed.cachedAt && parsed.timings) {
      const data = parsed as StoredCacheData;
      // Check if cache is expired
      if (Date.now() - data.cachedAt > CACHE_TTL_MS) {
        localStorage.removeItem(getStorageKey(meetingId));
        return {};
      }
      return data.timings;
    }

    // Backward compatibility: old format was just CachedTimingsState
    return parsed as CachedTimingsState;
  } catch {
    return {};
  }
}

/**
 * Save cached timings to localStorage for a meeting.
 * Removes the key if data is empty.
 */
export function saveCachedTimings(
  meetingId: string,
  data: CachedTimingsState
): void {
  if (typeof window === 'undefined') return;
  try {
    if (Object.keys(data).length === 0) {
      localStorage.removeItem(getStorageKey(meetingId));
    } else {
      const storedData: StoredCacheData = {
        cachedAt: Date.now(),
        timings: data,
      };
      localStorage.setItem(
        getStorageKey(meetingId),
        JSON.stringify(storedData)
      );
    }
  } catch {
    console.error('Failed to save timing cache to localStorage');
  }
}

/**
 * Clear cached timings from localStorage for a meeting.
 */
export function clearCachedTimings(meetingId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(getStorageKey(meetingId));
}

/**
 * Get the total count of unsaved timing entries across all segments.
 */
export function getUnsavedCount(data: CachedTimingsState): number {
  return Object.values(data).reduce(
    (total, seg) => total + seg.entries.length,
    0
  );
}

/**
 * Check if a specific segment has unsaved timing.
 */
export function hasUnsavedTiming(
  data: CachedTimingsState,
  segmentId: string
): boolean {
  return segmentId in data;
}

/**
 * Clean up expired timing caches from localStorage.
 * Removes all timing_cache_* entries older than 24 hours.
 * Call this on app initialization to prevent localStorage bloat.
 */
export function cleanupExpiredCaches(): void {
  if (typeof window === 'undefined') return;
  try {
    const keysToRemove: string[] = [];
    const now = Date.now();

    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(STORAGE_KEY_PREFIX)) continue;

      const raw = localStorage.getItem(key);
      if (!raw) continue;

      try {
        const parsed = JSON.parse(raw);
        // Check new format with timestamp
        if (parsed.cachedAt && parsed.timings) {
          if (now - parsed.cachedAt > CACHE_TTL_MS) {
            keysToRemove.push(key);
          }
        }
        // Old format without timestamp - can't determine age, leave it
      } catch {
        // Invalid JSON, remove it
        keysToRemove.push(key);
      }
    }

    keysToRemove.forEach((key) => localStorage.removeItem(key));
    if (keysToRemove.length > 0) {
      console.log(`Cleaned up ${keysToRemove.length} expired timing cache(s)`);
    }
  } catch {
    console.error('Failed to cleanup expired timing caches');
  }
}

/**
 * Load running timer state from sessionStorage for a meeting.
 * Returns null if no running timer or if it's for a different meeting.
 */
export function loadRunningTimer(
  meetingId: string
): Omit<RunningTimerState, 'meetingId'> | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(RUNNING_TIMER_KEY);
    if (!raw) return null;

    const state = JSON.parse(raw) as RunningTimerState;
    // Only return if for the same meeting
    if (state.meetingId !== meetingId) return null;

    // Return without meetingId (component doesn't need it)
    const { meetingId: _, ...rest } = state;
    void _; // Suppress unused variable warning
    return rest;
  } catch {
    return null;
  }
}

/**
 * Save running timer state to sessionStorage.
 * Clears the storage if state is null.
 */
export function saveRunningTimer(
  meetingId: string,
  state: Omit<RunningTimerState, 'meetingId'> | null
): void {
  if (typeof window === 'undefined') return;
  try {
    if (!state) {
      sessionStorage.removeItem(RUNNING_TIMER_KEY);
    } else {
      const fullState: RunningTimerState = { meetingId, ...state };
      sessionStorage.setItem(RUNNING_TIMER_KEY, JSON.stringify(fullState));
    }
  } catch {
    console.error('Failed to save running timer to sessionStorage');
  }
}

/**
 * Clear running timer from sessionStorage.
 */
export function clearRunningTimer(): void {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem(RUNNING_TIMER_KEY);
}
