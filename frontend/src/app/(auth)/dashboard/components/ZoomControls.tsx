interface ZoomControlsProps {
  window: number;
  canZoomIn: boolean;
  canZoomOut: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
}

export function ZoomControls({
  window,
  canZoomIn,
  canZoomOut,
  onZoomIn,
  onZoomOut,
}: ZoomControlsProps) {
  return (
    <div className='absolute top-0 right-[4%] flex items-center gap-1 z-10'>
      <span className='text-xs text-gray-500 mr-1'>{Math.round(window)}%</span>
      <button
        onClick={onZoomOut}
        disabled={!canZoomOut}
        className={`w-7 h-7 border rounded shadow-sm flex items-center justify-center text-base font-medium ${
          canZoomOut
            ? 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100'
            : 'bg-gray-100 border-gray-200 text-gray-300 cursor-not-allowed'
        }`}
      >
        −
      </button>
      <button
        onClick={onZoomIn}
        disabled={!canZoomIn}
        className={`w-7 h-7 border rounded shadow-sm flex items-center justify-center text-base font-medium ${
          canZoomIn
            ? 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100'
            : 'bg-gray-100 border-gray-200 text-gray-300 cursor-not-allowed'
        }`}
      >
        +
      </button>
    </div>
  );
}
