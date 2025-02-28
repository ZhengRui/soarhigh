export interface UserIF {
  uid: string;
  username: string;
  full_name: string;
}

export interface SegmentIF {
  segment_id: string;
  segment_type: string;
  start_time: string;
  duration: string;
  end_time?: string;
  role_taker?: string;
  title?: string;
  content?: string;
  related_segment_ids?: string;
}

export interface MeetingIF {
  meeting_type: string;
  theme: string;
  meeting_manager: string;
  date: string;
  start_time: string;
  end_time: string;
  location: string;
  introduction: string;
  segments: SegmentIF[];
  status?: 'draft' | 'published';
  id?: string;
}

export interface AwardIF {
  category: string;
  winner: string;
}
