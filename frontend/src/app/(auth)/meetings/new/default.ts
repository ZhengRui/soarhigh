import { SegmentIF, MeetingIF } from '@/interfaces';
import { getNextWednesday } from '@/utils/utils';

type EditableConfig = {
  editable: boolean;
  placeholder: string;
};

interface EditableSegmentIF extends SegmentIF {
  title_config: EditableConfig;
  content_config: EditableConfig;
  role_taker_config: EditableConfig;
}

export interface SegmentParams {
  segment_id: string;
  segment_type?: string;
  start_time: string;
  duration: string;
  related_segment_ids?: string;
}

export class BaseSegment implements EditableSegmentIF {
  segment_id: string = '';
  segment_type: string = '';
  start_time: string = '';
  duration: string = '';
  end_time: string = '';
  role_taker: string = '';
  title: string = '';
  content: string = '';
  related_segment_ids: string = '';

  role_taker_config: EditableConfig = {
    editable: true,
    placeholder: 'Assign role taker',
  };
  title_config: EditableConfig = { editable: false, placeholder: '' };
  content_config: EditableConfig = { editable: false, placeholder: '' };

  constructor(params: {
    segment_id: string;
    start_time: string;
    duration: string;
  }) {
    this.segment_id = params.segment_id;
    this.start_time = params.start_time;
    this.duration = params.duration;
  }
}

export class CustomSegment extends BaseSegment {
  constructor({
    segment_id,
    segment_type = 'Custom segment',
    start_time,
    duration,
  }: SegmentParams) {
    super({ segment_id, start_time, duration });
    this.segment_type = segment_type;
  }

  title_config = { editable: true, placeholder: 'Enter title (optional)' };
  content_config = { editable: true, placeholder: 'Enter content (optional)' };
  role_taker_config = { editable: true, placeholder: 'Assign role taker' };
}

export class WarmUpSegment extends BaseSegment {
  segment_type = 'Members and Guests Registration, Warm up';
  role_taker_config = { editable: false, placeholder: 'All attendees' };
}

export class SAASegment extends BaseSegment {
  segment_type = 'Meeting Rules Introduction (SAA)';
  role_taker_config = { editable: true, placeholder: 'Assign SAA' };
}

export class OpeningRemarksSegment extends BaseSegment {
  segment_type = 'Opening Remarks (President)';
}

export class TOMIntroSegment extends BaseSegment {
  segment_type = 'TOM (Toastmaster of Meeting) Introduction';
  role_taker_config = { editable: true, placeholder: 'Assign TOM' };
}

export class TimerIntroSegment extends BaseSegment {
  segment_type = 'Timer';
  role_taker_config = { editable: true, placeholder: 'Assign timer' };
}

export class HarkMasterIntroSegment extends BaseSegment {
  segment_type = 'Hark Master';
  role_taker_config = { editable: true, placeholder: 'Assign hark master' };
}

export class GuestsIntroSegment extends BaseSegment {
  segment_type = 'Guests Self Introduction (30s per guest)';
  role_taker_config = {
    editable: true,
    placeholder: 'Assign guest introduction host',
  };
}

export class TTMOpeningSegment extends BaseSegment {
  segment_type = 'TTM (Table Topic Master) Opening';
  role_taker_config = { editable: true, placeholder: 'Assign TTM' };
}

export class TableTopicSessionSegment extends BaseSegment {
  segment_type = 'Table Topic Session';
  content_config = { editable: true, placeholder: 'Enter WOT (Word of Today)' };
  role_taker_config = { editable: false, placeholder: '' };
}

export class PreparedSpeechSegment extends BaseSegment {
  segment_type: string;
  role_taker_config = { editable: true, placeholder: 'Assign Speaker' };
  title_config = { editable: true, placeholder: 'Enter title (optional)' };

  constructor(params: SegmentParams, speechNumber?: number) {
    super(params);
    this.segment_type = `Prepared Speech ${speechNumber || ''}`;
  }
}

export class TeaBreakSegment extends BaseSegment {
  segment_type = 'Tea Break & Group Photos';
  role_taker_config = { editable: false, placeholder: '' };
}

export class TableTopicEvalSegment extends BaseSegment {
  segment_type = 'Table Topic Evaluation';
  role_taker_config = { editable: true, placeholder: 'Assign evaluator' };
}

export class PreparedSpeechEvalSegment extends BaseSegment {
  segment_type: string;
  role_taker_config = { editable: true, placeholder: 'Assign evaluator' };

  constructor(
    {
      segment_id,
      start_time,
      duration,
      related_segment_ids = '',
    }: SegmentParams,
    speechNumber?: number
  ) {
    super({ segment_id, start_time, duration });
    this.segment_type = `Prepared Speech ${speechNumber || ''} Evaluation`;
    this.related_segment_ids = related_segment_ids;
  }
}

export class TimerReportSegment extends BaseSegment {
  segment_type = "Timer's Report";
  role_taker_config = { editable: false, placeholder: '' };
}

export class GeneralEvalSegment extends BaseSegment {
  segment_type = 'General Evaluation';
  role_taker_config = { editable: true, placeholder: 'Assign evaluator' };
}

export class VotingSegment extends BaseSegment {
  segment_type = 'Voting Section (TOM)';
  role_taker_config = { editable: false, placeholder: '' };
}

export class AwardsSegment extends BaseSegment {
  segment_type = 'Awards (President)';
  role_taker_config = { editable: false, placeholder: '' };
}

export class ClosingRemarksSegment extends BaseSegment {
  segment_type = 'Closing Remarks (President)';
  role_taker_config = { editable: false, placeholder: '' };
}

export const DEFAULT_SEGMENTS_REGULAR_MEETING: BaseSegment[] = [
  new WarmUpSegment({ segment_id: '1', start_time: '19:15', duration: '15' }),
  new SAASegment({ segment_id: '2', start_time: '19:30', duration: '3' }),
  new OpeningRemarksSegment({
    segment_id: '3',
    start_time: '19:33',
    duration: '2',
  }),
  new TOMIntroSegment({ segment_id: '4', start_time: '19:35', duration: '2' }),
  new TimerIntroSegment({
    segment_id: '5',
    start_time: '19:37',
    duration: '3',
  }),
  new HarkMasterIntroSegment({
    segment_id: '6',
    start_time: '19:40',
    duration: '3',
  }),
  new GuestsIntroSegment({
    segment_id: '7',
    start_time: '19:43',
    duration: '8',
  }),
  new TTMOpeningSegment({
    segment_id: '8',
    start_time: '19:52',
    duration: '4',
  }),
  new TableTopicSessionSegment({
    segment_id: '9',
    start_time: '19:56',
    duration: '16',
  }),
  new PreparedSpeechSegment(
    { segment_id: '10', start_time: '20:13', duration: '7' },
    1
  ),
  new PreparedSpeechSegment(
    { segment_id: '11', start_time: '20:21', duration: '7' },
    2
  ),
  new TeaBreakSegment({
    segment_id: '12',
    start_time: '20:29',
    duration: '12',
  }),
  new TableTopicEvalSegment({
    segment_id: '13',
    start_time: '20:42',
    duration: '7',
  }),
  new PreparedSpeechEvalSegment(
    {
      segment_id: '14',
      start_time: '20:50',
      duration: '3',
      related_segment_ids: '10',
    },
    1
  ),
  new PreparedSpeechEvalSegment(
    {
      segment_id: '15',
      start_time: '20:54',
      duration: '3',
      related_segment_ids: '11',
    },
    2
  ),
  new TimerReportSegment({
    segment_id: '16',
    start_time: '20:58',
    duration: '2',
  }),
  new GeneralEvalSegment({
    segment_id: '17',
    start_time: '21:01',
    duration: '4',
  }),
  new VotingSegment({ segment_id: '18', start_time: '21:06', duration: '2' }),
  new AwardsSegment({ segment_id: '19', start_time: '21:09', duration: '3' }),
  new ClosingRemarksSegment({
    segment_id: '20',
    start_time: '21:13',
    duration: '2',
  }),
];

export const DEFAULT_REGULAR_MEETING: Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
} = {
  meeting_type: 'Regular',
  theme: '',
  meeting_manager: '',
  date: getNextWednesday().date,
  start_time: '19:15',
  end_time: '21:30',
  location:
    "JOININ HUB, 6th Xin'an Rd, Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
  introduction: '',
  segments: DEFAULT_SEGMENTS_REGULAR_MEETING,
};

// Create a dummy params object for temporary instances
const dummyParams = { segment_id: '', start_time: '', duration: '' };

export const SEGMENT_TYPE_MAP = {
  [new WarmUpSegment(dummyParams).segment_type]: WarmUpSegment,
  [new SAASegment(dummyParams).segment_type]: SAASegment,
  [new OpeningRemarksSegment(dummyParams).segment_type]: OpeningRemarksSegment,
  [new TOMIntroSegment(dummyParams).segment_type]: TOMIntroSegment,
  [new TimerIntroSegment(dummyParams).segment_type]: TimerIntroSegment,
  [new HarkMasterIntroSegment(dummyParams).segment_type]:
    HarkMasterIntroSegment,
  [new GuestsIntroSegment(dummyParams).segment_type]: GuestsIntroSegment,
  [new TTMOpeningSegment(dummyParams).segment_type]: TTMOpeningSegment,
  [new TableTopicSessionSegment(dummyParams).segment_type]:
    TableTopicSessionSegment,
  'Prepared Speech': PreparedSpeechSegment, // Special case since it includes a number
  [new TeaBreakSegment(dummyParams).segment_type]: TeaBreakSegment,
  [new TableTopicEvalSegment(dummyParams).segment_type]: TableTopicEvalSegment,
  'Prepared Speech Evaluation': PreparedSpeechEvalSegment, // Special case since it includes a number
  [new TimerReportSegment(dummyParams).segment_type]: TimerReportSegment,
  [new GeneralEvalSegment(dummyParams).segment_type]: GeneralEvalSegment,
  [new VotingSegment(dummyParams).segment_type]: VotingSegment,
  [new AwardsSegment(dummyParams).segment_type]: AwardsSegment,
  [new ClosingRemarksSegment(dummyParams).segment_type]: ClosingRemarksSegment,
  [new CustomSegment(dummyParams).segment_type]: CustomSegment,
} as const;

export type SegmentType = keyof typeof SEGMENT_TYPE_MAP;
