import type { MeetingOptionIF } from '@/interfaces';

type MeetingLabelData = Pick<MeetingOptionIF, 'type' | 'no'>;

export function isEventMeeting(meeting: MeetingLabelData | null) {
  return Boolean(meeting?.no && String(meeting.no).startsWith('10000'));
}

export function formatMeetingType(meeting: MeetingLabelData) {
  return isEventMeeting(meeting) ? 'Event' : meeting.type;
}

export function formatMeetingLabel(meeting: MeetingOptionIF) {
  return `${formatMeetingType(meeting)}${meeting.no ? ` #${meeting.no}` : ''}`;
}
