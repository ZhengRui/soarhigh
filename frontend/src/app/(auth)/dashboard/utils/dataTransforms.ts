import { MemberMeetingRecordIF, MeetingAttendanceRecordIF } from '@/interfaces';
import { MemberAttendanceData, MeetingAttendanceChartData } from './types';

/**
 * Transform raw member meeting records into aggregated attendance data.
 * Groups by member, counts unique meetings, and sorts by attendance count.
 */
export function transformMemberAttendanceData(
  memberMeetings: MemberMeetingRecordIF[]
): MemberAttendanceData[] {
  if (!memberMeetings?.length) return [];

  // Group by member
  const memberMap = new Map<
    string,
    {
      fullName: string;
      meetings: Map<string, { theme: string; date: string; roles: string[] }>;
    }
  >();

  memberMeetings.forEach((record) => {
    if (!memberMap.has(record.member_id)) {
      memberMap.set(record.member_id, {
        fullName: record.full_name,
        meetings: new Map(),
      });
    }

    const memberData = memberMap.get(record.member_id)!;
    if (!memberData.meetings.has(record.meeting_id)) {
      memberData.meetings.set(record.meeting_id, {
        theme: record.meeting_theme,
        date: record.meeting_date,
        roles: [],
      });
    }
    memberData.meetings.get(record.meeting_id)!.roles.push(record.role);
  });

  // Convert to array and sort by meeting count
  const result: MemberAttendanceData[] = [];
  memberMap.forEach((value) => {
    const meetings = Array.from(value.meetings.values()).sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
    );
    result.push({
      name: value.fullName.split(' ')[0], // First name for chart label
      fullName: value.fullName,
      meetingCount: meetings.length,
      meetings,
    });
  });

  return result.sort((a, b) => b.meetingCount - a.meetingCount);
}

/**
 * Transform raw meeting attendance records into chart data.
 * Truncates long theme names for display.
 */
export function transformMeetingAttendanceData(
  meetingAttendance: MeetingAttendanceRecordIF[]
): MeetingAttendanceChartData[] {
  if (!meetingAttendance?.length) return [];

  return meetingAttendance.map((record) => ({
    label:
      record.meeting_theme.length > 10
        ? record.meeting_theme.slice(0, 10) + '...'
        : record.meeting_theme,
    date: record.meeting_date,
    theme: record.meeting_theme,
    memberCount: record.member_count,
    guestCount: record.guest_count,
    memberNames: record.member_names,
    guestNames: record.guest_names,
  }));
}
