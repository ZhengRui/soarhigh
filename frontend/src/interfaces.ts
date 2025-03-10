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

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type PaginatedMeetings = PaginatedResponse<MeetingIF>;
export type PaginatedPosts = PaginatedResponse<PostIF>;
