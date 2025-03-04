import { SegmentIF, MeetingIF, AttendeeIF } from '@/interfaces';
import { getNextWednesday } from '@/utils/utils';

type EditableConfig = {
  editable: boolean;
  placeholder: string;
};

interface EditableSegmentIF extends SegmentIF {
  title_config: EditableConfig;
  content_config: EditableConfig;
  role_taker_config: EditableConfig;
  related_segment_ids_config: EditableConfig;
}

export interface SegmentParams {
  id: string;
  type?: string;
  start_time: string;
  duration: string;
  related_segment_ids?: string;
}

export class BaseSegment implements EditableSegmentIF {
  id: string = '';
  type: string = '';
  start_time: string = '';
  duration: string = '';
  end_time: string = '';
  role_taker: AttendeeIF | undefined = undefined;
  title: string = '';
  content: string = '';
  related_segment_ids: string = '';

  role_taker_config: EditableConfig = {
    editable: true,
    placeholder: 'Assign role taker',
  };
  title_config: EditableConfig = { editable: false, placeholder: '' };
  content_config: EditableConfig = { editable: false, placeholder: '' };
  related_segment_ids_config: EditableConfig = {
    editable: false,
    placeholder: '',
  };

  constructor(params: { id: string; start_time: string; duration: string }) {
    this.id = params.id;
    this.start_time = params.start_time;
    this.duration = params.duration;
  }
}

export class CustomSegment extends BaseSegment {
  constructor({
    id,
    type = 'Custom segment',
    start_time,
    duration,
  }: SegmentParams) {
    super({ id, start_time, duration });
    this.type = type;
  }

  title_config = { editable: true, placeholder: 'Enter title (optional)' };
  content_config = { editable: true, placeholder: 'Enter content (optional)' };
  role_taker_config = { editable: true, placeholder: 'Assign role taker' };
}

export class WarmUpSegment extends BaseSegment {
  type = 'Members and Guests Registration, Warm up';
  role_taker_config = { editable: false, placeholder: 'All attendees' };
}

export class SAASegment extends BaseSegment {
  type = 'Meeting Rules Introduction (SAA)';
  role_taker_config = { editable: true, placeholder: 'Assign SAA' };
}

export class OpeningRemarksSegment extends BaseSegment {
  type = 'Opening Remarks (President)';
}

export class TOMIntroSegment extends BaseSegment {
  type = 'TOM (Toastmaster of Meeting) Introduction';
  role_taker_config = { editable: true, placeholder: 'Assign TOM' };
}

export class TimerIntroSegment extends BaseSegment {
  type = 'Timer';
  role_taker_config = { editable: true, placeholder: 'Assign timer' };
}

export class HarkMasterIntroSegment extends BaseSegment {
  type = 'Hark Master';
  role_taker_config = { editable: true, placeholder: 'Assign hark master' };
}

export class GuestsIntroSegment extends BaseSegment {
  type = 'Guests Self Introduction (30s per guest)';
  role_taker_config = {
    editable: true,
    placeholder: 'Assign guest introduction host',
  };
}

export class TTMOpeningSegment extends BaseSegment {
  type = 'TTM (Table Topic Master) Opening';
  role_taker_config = { editable: true, placeholder: 'Assign TTM' };
}

export class TableTopicSessionSegment extends BaseSegment {
  type = 'Table Topic Session';
  content_config = { editable: true, placeholder: 'Enter WOT (Word of Today)' };
  role_taker_config = { editable: false, placeholder: '' };
}

export class PreparedSpeechSegment extends BaseSegment {
  type: string;
  role_taker_config = { editable: true, placeholder: 'Assign Speaker' };
  title_config = { editable: true, placeholder: 'Enter title (optional)' };

  constructor(params: SegmentParams, speechNumber?: number) {
    super(params);
    this.type =
      speechNumber !== undefined
        ? `Prepared Speech ${speechNumber}`
        : 'Prepared Speech';
  }
}

export class TeaBreakSegment extends BaseSegment {
  type = 'Tea Break & Group Photos';
  role_taker_config = { editable: false, placeholder: '' };
}

export class TableTopicEvalSegment extends BaseSegment {
  type = 'Table Topic Evaluation';
  role_taker_config = { editable: true, placeholder: 'Assign evaluator' };
}

export class PreparedSpeechEvalSegment extends BaseSegment {
  type: string;
  role_taker_config = { editable: true, placeholder: 'Assign evaluator' };
  related_segment_ids_config = {
    editable: true,
    placeholder: 'Add related speech',
  };

  constructor(
    { id, start_time, duration, related_segment_ids = '' }: SegmentParams,
    speechNumber?: number
  ) {
    super({ id, start_time, duration });
    this.type =
      speechNumber !== undefined
        ? `Prepared Speech ${speechNumber} Evaluation`
        : 'Prepared Speech Evaluation';
    this.related_segment_ids = related_segment_ids;
  }
}

export class TimerReportSegment extends BaseSegment {
  type = "Timer's Report";
  role_taker_config = { editable: false, placeholder: '' };
}

export class GeneralEvalSegment extends BaseSegment {
  type = 'General Evaluation';
  role_taker_config = { editable: true, placeholder: 'Assign evaluator' };
  related_segment_ids_config = {
    editable: true,
    placeholder: 'Add related segments',
  };
}

export class VotingSegment extends BaseSegment {
  type = 'Voting Section (TOM)';
  role_taker_config = { editable: false, placeholder: '' };
}

export class AwardsSegment extends BaseSegment {
  type = 'Awards (President)';
  role_taker_config = { editable: false, placeholder: '' };
}

export class ClosingRemarksSegment extends BaseSegment {
  type = 'Closing Remarks (President)';
  role_taker_config = { editable: false, placeholder: '' };
}

export const DEFAULT_SEGMENTS_REGULAR_MEETING: BaseSegment[] = [
  new WarmUpSegment({ id: '1', start_time: '19:15', duration: '15' }),
  new SAASegment({ id: '2', start_time: '19:30', duration: '3' }),
  new OpeningRemarksSegment({
    id: '3',
    start_time: '19:33',
    duration: '2',
  }),
  new TOMIntroSegment({ id: '4', start_time: '19:35', duration: '2' }),
  new TimerIntroSegment({
    id: '5',
    start_time: '19:37',
    duration: '3',
  }),
  new HarkMasterIntroSegment({
    id: '6',
    start_time: '19:40',
    duration: '3',
  }),
  new GuestsIntroSegment({
    id: '7',
    start_time: '19:43',
    duration: '8',
  }),
  new TTMOpeningSegment({
    id: '8',
    start_time: '19:52',
    duration: '4',
  }),
  new TableTopicSessionSegment({
    id: '9',
    start_time: '19:56',
    duration: '16',
  }),
  new PreparedSpeechSegment(
    { id: '10', start_time: '20:13', duration: '7' },
    1
  ),
  new PreparedSpeechSegment(
    { id: '11', start_time: '20:21', duration: '7' },
    2
  ),
  new TeaBreakSegment({
    id: '12',
    start_time: '20:29',
    duration: '12',
  }),
  new TableTopicEvalSegment({
    id: '13',
    start_time: '20:42',
    duration: '7',
  }),
  new PreparedSpeechEvalSegment(
    {
      id: '14',
      start_time: '20:50',
      duration: '3',
      related_segment_ids: '10',
    },
    1
  ),
  new PreparedSpeechEvalSegment(
    {
      id: '15',
      start_time: '20:54',
      duration: '3',
      related_segment_ids: '11',
    },
    2
  ),
  new TimerReportSegment({
    id: '16',
    start_time: '20:58',
    duration: '2',
  }),
  new GeneralEvalSegment({
    id: '17',
    start_time: '21:01',
    duration: '4',
  }),
  new VotingSegment({ id: '18', start_time: '21:06', duration: '2' }),
  new AwardsSegment({ id: '19', start_time: '21:09', duration: '3' }),
  new ClosingRemarksSegment({
    id: '20',
    start_time: '21:13',
    duration: '2',
  }),
];

export const DEFAULT_REGULAR_MEETING: Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
} = {
  type: 'Regular',
  no: undefined,
  theme: '',
  manager: undefined,
  date: getNextWednesday().date,
  start_time: '19:15',
  end_time: '21:30',
  location:
    "JOININ HUB, 6th Xin'an Rd, Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
  introduction: '',
  segments: DEFAULT_SEGMENTS_REGULAR_MEETING,
};

export const DEFAULT_WORKSHOP_MEETING: Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
} = {
  type: 'Workshop',
  no: undefined,
  theme: '',
  manager: undefined,
  date: getNextWednesday().date,
  start_time: '19:15',
  end_time: '21:30',
  location:
    "JOININ HUB, 6th Xin'an Rd, Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
  introduction: '',
  segments: [],
};

export const DEFAULT_CUSTOM_MEETING: Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
} = {
  type: 'Custom',
  no: undefined,
  theme: '',
  manager: undefined,
  date: getNextWednesday().date,
  start_time: '19:15',
  end_time: '21:30',
  location:
    "JOININ HUB, 6th Xin'an Rd, Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
  introduction: '',
  segments: [
    new CustomSegment({
      id: '1',
      type: 'New segment',
      start_time: '19:15',
      duration: '15',
    }),
  ],
};

// Create a dummy params object for temporary instances
const dummyParams = { id: '', start_time: '', duration: '' };

export const SEGMENT_TYPE_MAP = {
  [new WarmUpSegment(dummyParams).type]: WarmUpSegment,
  [new SAASegment(dummyParams).type]: SAASegment,
  [new OpeningRemarksSegment(dummyParams).type]: OpeningRemarksSegment,
  [new TOMIntroSegment(dummyParams).type]: TOMIntroSegment,
  [new TimerIntroSegment(dummyParams).type]: TimerIntroSegment,
  [new HarkMasterIntroSegment(dummyParams).type]: HarkMasterIntroSegment,
  [new GuestsIntroSegment(dummyParams).type]: GuestsIntroSegment,
  [new TTMOpeningSegment(dummyParams).type]: TTMOpeningSegment,
  [new TableTopicSessionSegment(dummyParams).type]: TableTopicSessionSegment,
  'Prepared Speech': PreparedSpeechSegment, // Special case since it includes a number
  [new TeaBreakSegment(dummyParams).type]: TeaBreakSegment,
  [new TableTopicEvalSegment(dummyParams).type]: TableTopicEvalSegment,
  'Prepared Speech Evaluation': PreparedSpeechEvalSegment, // Special case since it includes a number
  [new TimerReportSegment(dummyParams).type]: TimerReportSegment,
  [new GeneralEvalSegment(dummyParams).type]: GeneralEvalSegment,
  [new VotingSegment(dummyParams).type]: VotingSegment,
  [new AwardsSegment(dummyParams).type]: AwardsSegment,
  [new ClosingRemarksSegment(dummyParams).type]: ClosingRemarksSegment,
  [new CustomSegment(dummyParams).type]: CustomSegment,
} as const;

export type SegmentType = keyof typeof SEGMENT_TYPE_MAP;
