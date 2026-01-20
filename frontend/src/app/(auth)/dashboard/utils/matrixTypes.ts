import { MatrixRoleKey } from './roleMapping';

export interface MemberInfo {
  memberId: string;
  fullName: string;
  shortName: string;
}

export interface MeetingInfo {
  meetingId: string;
  date: string;
  theme: string;
  meetingNo?: number;
}

export interface MatrixCellData {
  count: number;
  meetingIds: string[];
}

export interface MatrixData {
  members: MemberInfo[];
  meetings: MeetingInfo[];
  // matrix[roleKey][memberId] = { count, meetingIds }
  matrix: Record<MatrixRoleKey, Record<string, MatrixCellData>>;
  // Lookup: which meetings did a member attend for any role
  memberMeetings: Record<string, string[]>;
  // Lookup: which meetings had a specific role filled
  roleMeetings: Record<MatrixRoleKey, string[]>;
}

export type HighlightMode =
  | { type: 'none' }
  | {
      type: 'cell';
      memberId: string;
      roleKey: MatrixRoleKey;
      meetingIds: string[];
    }
  | { type: 'column'; memberId: string; meetingIds: string[] }
  | { type: 'row'; roleKey: MatrixRoleKey; meetingIds: string[] };
