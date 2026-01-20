import { useRef, useCallback } from 'react';
import { MeetingInfo } from '../utils/matrixTypes';
import { MatrixHighlightState } from '../hooks/useMatrixHighlight';

const DOUBLE_TAP_DELAY = 300; // ms

interface MeetingPillProps {
  meeting: MeetingInfo;
  isHighlighted: boolean;
  isDimmed: boolean;
  onSelect: () => void;
}

function MeetingPill({
  meeting,
  isHighlighted,
  isDimmed,
  onSelect,
}: MeetingPillProps) {
  const lastTapTime = useRef<number>(0);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const now = Date.now();
      if (now - lastTapTime.current < DOUBLE_TAP_DELAY) {
        e.preventDefault();
        onSelect();
        lastTapTime.current = 0;
      } else {
        lastTapTime.current = now;
      }
    },
    [onSelect]
  );

  return (
    <div
      title={meeting.theme}
      className={`flex flex-col items-center px-3 py-2 rounded-lg border transition-all duration-150 min-w-[100px] cursor-pointer select-none ${
        isHighlighted
          ? 'ring-1 ring-purple-500 bg-purple-50 border-purple-300'
          : isDimmed
            ? 'opacity-30 border-gray-200'
            : 'border-gray-200 hover:bg-gray-50'
      }`}
      onDoubleClick={onSelect}
      onTouchEnd={handleTouchEnd}
    >
      <span className='text-xs font-medium text-gray-900 truncate max-w-[80px]'>
        {meeting.theme.length > 12
          ? meeting.theme.slice(0, 12) + '...'
          : meeting.theme}
      </span>
      <span className='text-xs text-gray-500'>{meeting.date}</span>
      {meeting.meetingNo && (
        <span className='text-xs text-purple-600 font-medium'>
          #{meeting.meetingNo}
        </span>
      )}
    </div>
  );
}

interface MeetingPillsListProps {
  meetings: MeetingInfo[];
  highlightState: MatrixHighlightState;
}

export function MeetingPillsList({
  meetings,
  highlightState,
}: MeetingPillsListProps) {
  const hasHighlight = highlightState.highlight.type !== 'none';

  return (
    <div className='overflow-x-auto p-1'>
      <div className='inline-flex gap-2'>
        {meetings.map((meeting) => {
          const isHighlighted = highlightState.isMeetingHighlighted(
            meeting.meetingId
          );
          const isDimmed = hasHighlight && !isHighlighted;

          return (
            <MeetingPill
              key={meeting.meetingId}
              meeting={meeting}
              isHighlighted={isHighlighted}
              isDimmed={isDimmed}
              onSelect={() =>
                highlightState.handleMeetingDoubleClick(meeting.meetingId)
              }
            />
          );
        })}
      </div>
    </div>
  );
}
