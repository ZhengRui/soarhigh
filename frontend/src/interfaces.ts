export interface UserIF {
  uid: string;
  username: string;
  full_name: string;
}

export interface SegmentIF {
  id: string;
  type: string;
  start_time: string;
  duration: string;
  end_time?: string;
  role_taker?: AttendeeIF;
  title?: string;
  content?: string;
  related_segment_ids?: string;
}

export interface AttendeeIF {
  id?: string;
  name: string;
  member_id: string;
}

export interface MediaIF {
  id?: string;
  filename: string;
  url: string;
  fileKey: string;
  uploadedAt: string;
}

export interface MeetingIF {
  id?: string;
  type: string;
  no?: number;
  theme: string;
  manager?: AttendeeIF;
  date: string;
  start_time: string;
  end_time: string;
  location: string;
  introduction: string;
  segments: SegmentIF[];
  status?: 'draft' | 'published';
  awards?: AwardIF[];
  media?: MediaIF[];
}

export interface AwardIF {
  meeting_id: string;
  category: string;
  winner: string;
}

export interface PostIF {
  id: string;
  title: string;
  slug: string;
  content: string;
  is_public: boolean;
  author: {
    member_id: string;
    name: string;
  };
  created_at?: string;
  updated_at?: string;
}

export interface CandidateIF {
  name: string;
  segment?: string;
  count?: number;
}

export interface CategoryCandidatesIF {
  category: string;
  candidates: CandidateIF[];
}

export interface VoteRecordIF {
  category: string;
  name: string;
}

export interface VoteIF {
  id?: string;
  meeting_id: string;
  category: string;
  name: string;
  segment?: string;
  count: number;
}

export interface VoteStatusIF {
  id?: string;
  meeting_id: string;
  open: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type PaginatedMeetings = PaginatedResponse<MeetingIF>;
export type PaginatedPosts = PaginatedResponse<PostIF>;

// Dashboard Stats Interfaces
export interface MemberMeetingRecordIF {
  member_id: string;
  username: string;
  full_name: string;
  meeting_id: string;
  meeting_date: string;
  meeting_theme: string;
  meeting_no?: number;
  role: string;
}

export interface MeetingAttendanceRecordIF {
  meeting_id: string;
  meeting_date: string;
  meeting_theme: string;
  meeting_no?: number;
  member_count: number;
  guest_count: number;
  member_names: string[];
  guest_names: string[];
}

export interface DashboardStatsIF {
  member_meetings: MemberMeetingRecordIF[];
  meeting_attendance: MeetingAttendanceRecordIF[];
}

// Checkin Interfaces
export interface CheckinIF {
  id: string;
  meeting_id: string;
  wxid: string;
  segment_id: string | null;
  name: string | null;
  referral_source: string | null;
  is_member: boolean;
  created_at: string;
  updated_at: string;
}

// Timing Interfaces
export interface TimingIF {
  id?: string;
  meeting_id: string;
  segment_id: string;
  name?: string | null;
  planned_duration_minutes: number;
  actual_start_time: string;
  actual_end_time: string;
  actual_duration_seconds: number;
  dot_color: 'gray' | 'green' | 'yellow' | 'red' | 'bell';
  created_at?: string;
  updated_at?: string;
}

export interface TimingsListResponseIF {
  can_control: boolean;
  timings: TimingIF[];
}

export interface TimingCreateIF {
  segment_id: string;
  name?: string | null;
  planned_duration_minutes: number;
  actual_start_time: string;
  actual_end_time: string;
}

export interface TimingBatchItemIF {
  name: string;
  planned_duration_minutes: number;
  actual_start_time: string;
  actual_end_time: string;
}

export interface TimingBatchCreateIF {
  segment_id: string;
  timings: TimingBatchItemIF[];
}
