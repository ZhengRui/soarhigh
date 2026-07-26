import type { WePostRenderDocument } from '../types';

export const meetingRecapFixture: WePostRenderDocument = {
  schemaVersion: 1,
  renderVersion: 1,
  title: 'The Courage to Try the Next Sentence',
  slug: 'the-courage-to-try-the-next-sentence',
  excerpt:
    "At SoarHigh's 236th meeting, one small second attempt showed how learning becomes visible.",
  byline: 'SoarHigh Toastmasters Editorial Team',
  articleType: 'meeting-recap',
  sourceMeetingId: 'meeting-236',
  body: [
    {
      kind: 'markdown',
      source:
        'The room became quiet when Maya reached the front. She had prepared an opening, but the next sentence had disappeared.\n\nWhat happened after that mattered more than a polished speech. ==She stayed in the room and tried again.==\n',
      line: 1,
    },
    {
      kind: 'directive',
      name: 'info-grid',
      line: 5,
      payload: {
        title: 'Meeting at a glance',
        items: [
          { label: 'Theme', value: 'Learning in public' },
          { label: 'Date', value: 'July 18, 2026' },
          { label: 'Place', value: 'SoarHigh Club' },
        ],
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## First, make the attempt visible\n\nThe evening opened with three speakers sharing how they protect time for deeper work. Their methods differed, but each one turned an abstract intention into something observable.\n',
      line: 15,
    },
    {
      kind: 'directive',
      name: 'timeline',
      line: 20,
      payload: {
        title: 'How the evening unfolded',
        items: [
          {
            label: '19:30',
            title: 'Put the thought on paper',
            description:
              'Members captured distracting ideas before returning to the task.',
          },
          {
            label: '20:05',
            title: 'Say the unfinished version',
            description: 'Maya delivered the opening she had, then paused.',
          },
          {
            label: '20:20',
            title: 'Use feedback for another attempt',
            description: 'She returned with two clearer sentences.',
          },
        ],
      },
    },
    {
      kind: 'directive',
      name: 'gallery',
      line: 34,
      payload: {
        items: ['M01', 'M02', 'M03'],
        caption:
          'Three moments of members listening, responding, and trying again',
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## Then, make feedback usable\n\nThe evaluator did not decide whether Maya was a good speaker. He offered one visible next move: slow down in the middle of the stage, keep the opening, and add the example she had told us during the break.\n',
      line: 41,
    },
    {
      kind: 'directive',
      name: 'pull-quote',
      line: 46,
      payload: {
        text: 'I think I can add two more sentences.',
        attribution: 'Maya, after her first attempt',
      },
    },
    {
      kind: 'directive',
      name: 'person',
      line: 51,
      payload: {
        name: 'Maya Chen',
        role: 'First-time Table Topics speaker',
        media: 'M04',
        summary:
          'She returned to the stage after feedback and completed the thought she had left unfinished.',
        quote: 'I did not need a new speech. I needed one more try.',
      },
    },
    {
      kind: 'markdown',
      source:
        '\nThe second version was still brief. It was also more specific, more relaxed, and unmistakably hers. ==Useful feedback leaves the learner with somewhere to begin.==\n',
      line: 58,
    },
    {
      kind: 'directive',
      name: 'video',
      line: 61,
      payload: {
        media: 'V01',
        caption: 'Maya returns to the stage and completes her example',
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## What we can take into the next meeting\n\nLearning did not look like collecting every idea from the evening. It looked like speaking, being heard, receiving a concrete suggestion, and choosing to try once more.\n',
      line: 65,
    },
    {
      kind: 'directive',
      name: 'takeaway',
      line: 70,
      payload: {
        title: 'A small practice for this week',
        text: 'Capture the unfinished thought, ask for one concrete next move, and make a second attempt before judging the first.',
      },
    },
    {
      kind: 'markdown',
      source:
        '\nWe will remember the talks, photographs, and laughter. More importantly, we will remember that ==progress became visible when someone chose the next sentence.==',
      line: 74,
    },
  ],
  media: [
    {
      id: 'M01',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/weeklymeeting.jpg?x-oss-process=image/format,webp',
      description:
        'Members gather around the meeting room and listen to a speaker.',
      credit: 'SoarHigh Toastmasters',
      people: ['Club members'],
      include: true,
      order: 0,
      descriptionSource: 'user',
      descriptionStatus: 'confirmed',
    },
    {
      id: 'M02',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/workshop.jpg?x-oss-process=image/format,webp',
      description:
        'Members record ideas and compare notes during a club workshop.',
      credit: 'SoarHigh Toastmasters',
      people: ['Club members'],
      include: true,
      order: 1,
      descriptionSource: 'user',
      descriptionStatus: 'confirmed',
    },
    {
      id: 'M03',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/leadershiptraining.jpg?x-oss-process=image/format,webp',
      description:
        'An evaluator offers a concrete suggestion from the front of the room.',
      credit: 'SoarHigh Toastmasters',
      people: ['Meeting evaluator'],
      include: true,
      order: 2,
      descriptionSource: 'ai',
      descriptionStatus: 'confirmed',
    },
    {
      id: 'M04',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/competition.jpg?x-oss-process=image/format,webp',
      description: 'A speaker smiles after completing a second attempt.',
      credit: 'SoarHigh Toastmasters',
      people: ['Maya Chen'],
      include: true,
      order: 3,
      descriptionSource: 'user',
      descriptionStatus: 'confirmed',
    },
    {
      id: 'V01',
      kind: 'video',
      sourceUrl:
        'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4',
      posterUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/web/publicspeaking.jpeg?x-oss-process=image/format,webp',
      description:
        'A short video placeholder representing Maya returning to the stage.',
      credit: 'Renderer fixture video',
      people: ['Maya Chen'],
      include: true,
      order: 4,
      descriptionSource: 'user',
      descriptionStatus: 'confirmed',
    },
  ],
  coverMediaId: 'M01',
  presentation: {
    layout: 'brand-default',
    palette: 'paper-neutral',
    appearance: 'light',
    typeface: 'editorial-serif',
  },
};
