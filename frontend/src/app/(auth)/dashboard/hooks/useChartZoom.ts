import { useState, useCallback } from 'react';

export interface ZoomState {
  start: number;
  end: number;
}

const MIN_WINDOW = 20;
const ZOOM_STEP = 20;

const getZoomWindow = (state: ZoomState) => state.end - state.start;

const clampToBounds = (start: number, end: number): ZoomState => {
  let newStart = start;
  let newEnd = end;

  if (newStart < 0) {
    newEnd -= newStart;
    newStart = 0;
  }
  if (newEnd > 100) {
    newStart -= newEnd - 100;
    newEnd = 100;
  }

  return { start: Math.max(0, newStart), end: Math.min(100, newEnd) };
};

const zoomIn = (state: ZoomState): ZoomState => {
  const window = getZoomWindow(state);
  if (window <= MIN_WINDOW) return state;

  const center = (state.start + state.end) / 2;
  const newWindow = Math.max(MIN_WINDOW, window - ZOOM_STEP);

  return clampToBounds(center - newWindow / 2, center + newWindow / 2);
};

const zoomOut = (state: ZoomState): ZoomState => {
  const window = getZoomWindow(state);
  if (window >= 100) return state;

  const center = (state.start + state.end) / 2;
  const newWindow = Math.min(100, window + ZOOM_STEP);

  return clampToBounds(center - newWindow / 2, center + newWindow / 2);
};

export function useChartZoom(initialState: ZoomState = { start: 0, end: 100 }) {
  const [zoom, setZoom] = useState<ZoomState>(initialState);

  const handleZoomIn = useCallback(() => {
    setZoom((prev) => zoomIn(prev));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((prev) => zoomOut(prev));
  }, []);

  const reset = useCallback(() => {
    setZoom({ start: 0, end: 100 });
  }, []);

  const window = getZoomWindow(zoom);
  const canZoomIn = window > MIN_WINDOW;
  const canZoomOut = window < 100;

  // Sync with external zoom changes (e.g., from chart panning)
  const syncZoom = useCallback((start: number, end: number) => {
    setZoom({ start, end });
  }, []);

  return {
    zoom,
    window,
    canZoomIn,
    canZoomOut,
    handleZoomIn,
    handleZoomOut,
    reset,
    syncZoom,
  };
}
