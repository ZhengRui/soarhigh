export const MEETING_462 = {
  id: 'meeting-462',
  type: 'Regular',
  no: 462,
  theme: 'Culture, belonging, and the courage to speak',
  manager: {
    id: 'manager-462',
    member_id: 'albert',
    name: 'Albert Ding',
  },
  date: '2026-07-15',
  start_time: '19:15',
  end_time: '21:30',
  location: 'Gobel Power Energy · Shenzhen',
  introduction:
    'Food, clothes, festivals, and travel stories—culture is present in the ordinary details of everyday life. We grow up in different places, shaped by different customs, languages, and ways of seeing the world. Meeting 462 invites members and guests to share what feels familiar, what surprised them when travelling, and which traditions they would carry into a new home.\n\n吃的、穿的、过节怎么过、旅行去了哪里——这些日常细节里，都是文化的影子。随便聊，随便问，一起坐下来，把天南海北的生活都摊开来看看。',
  segments: [
    {
      id: 'segment-1',
      type: 'Registration and warm-up',
      start_time: '19:15',
      duration: '15',
      end_time: '19:30',
      role_taker: {
        member_id: 'reception',
        name: 'Reception team',
      },
    },
    {
      id: 'segment-2',
      type: 'Opening',
      start_time: '19:30',
      duration: '10',
      end_time: '19:40',
      role_taker: {
        member_id: 'tm',
        name: 'Albert Ding',
      },
    },
    {
      id: 'segment-3',
      type: 'Table Topics',
      start_time: '19:40',
      duration: '25',
      end_time: '20:05',
      role_taker: {
        member_id: 'joyce',
        name: 'Joyce Feng',
      },
      title: 'Culture in daily life',
    },
    {
      id: 'segment-4',
      type: 'Prepared Speech',
      start_time: '20:05',
      duration: '12',
      end_time: '20:17',
      role_taker: {
        member_id: 'rui',
        name: 'Rui Zheng',
      },
      title: 'A Tale of Two Homes',
    },
    {
      id: 'segment-5',
      type: 'Prepared Speech',
      start_time: '20:17',
      duration: '12',
      end_time: '20:29',
      role_taker: {
        member_id: 'nina',
        name: 'Nina',
      },
      title: 'Listening Across Cultures',
    },
    {
      id: 'segment-6',
      type: 'Evaluations',
      start_time: '20:29',
      duration: '31',
      end_time: '21:00',
      role_taker: {
        member_id: 'roc',
        name: 'Roc',
      },
    },
    {
      id: 'segment-7',
      type: 'Recognition and closing',
      start_time: '21:00',
      duration: '30',
      end_time: '21:30',
      role_taker: {
        member_id: 'albert',
        name: 'Albert Ding',
      },
    },
  ],
  status: 'published',
  awards: [
    {
      meeting_id: 'meeting-462',
      category: 'Best Prepared Speaker',
      winner: 'Rui Zheng',
    },
    {
      meeting_id: 'meeting-462',
      category: 'Best Table Topic Speaker',
      winner: 'Nina',
    },
  ],
};

export const MEETING_461 = {
  ...MEETING_462,
  id: 'meeting-461',
  type: 'Workshop',
  no: 461,
  date: '2026-07-08',
  theme: 'Build a speech people remember',
  introduction:
    'A practical workshop for shaping a clear idea into a memorable speech.',
  segments: [
    {
      id: 'workshop-segment',
      type: 'Workshop',
      start_time: '19:30',
      duration: '90',
      end_time: '21:00',
      role_taker: {
        member_id: 'facilitator',
        name: 'Workshop facilitator',
      },
      title: 'From idea to stage',
    },
  ],
  awards: [],
};

export const MEETING_449 = {
  ...MEETING_461,
  id: 'meeting-449',
  type: 'Special Event',
  no: 100001,
  date: '2026-04-08',
  theme: 'Beyond the Mask: Authenticity in Connection',
};

export const FIRST_SOURCE_KEY = 'M01';
export const FIRST_FILE_KEY = 'meetings/462/meeting-room.jpg';

export const MEETING_OPTIONS = [
  MEETING_462,
  MEETING_461,
  ...Array.from({ length: 98 }, (_, index) => ({
    ...MEETING_461,
    id: `meeting-extra-${index + 1}`,
    no: 1000 - index,
    theme: `Meeting theme ${1000 - index}`,
  })),
  MEETING_449,
];
