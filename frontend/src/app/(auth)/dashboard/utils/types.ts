// Aggregated data for Member Attendance Chart
export interface MemberAttendanceData {
  name: string;
  fullName: string;
  meetingCount: number;
  meetings: { theme: string; date: string; roles: string[] }[];
}

// Aggregated data for Meeting Attendance Chart
export interface MeetingAttendanceChartData {
  label: string;
  date: string;
  theme: string;
  memberCount: number;
  guestCount: number;
  memberNames: string[];
  guestNames: string[];
}
