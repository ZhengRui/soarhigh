import type { WePostRenderDocument } from '../types';

export const eventPreviewFixture: WePostRenderDocument = {
  schemaVersion: 1,
  renderVersion: 1,
  title: 'An Evening for Stories That Move',
  slug: 'an-evening-for-stories-that-move',
  excerpt:
    'A practical SoarHigh workshop for turning a useful idea into a story people can follow and remember.',
  byline: 'SoarHigh Toastmasters Program Team',
  articleType: 'event-preview',
  body: [
    {
      kind: 'markdown',
      source:
        'A strong story does more than decorate an idea. It helps an audience understand why the idea matters and what changed because of it.\n\nOn August 15, SoarHigh will open its meeting room for an evening of short demonstrations, guided practice, and supportive feedback. No prepared speech is required.\n',
      line: 1,
    },
    {
      kind: 'directive',
      name: 'info-grid',
      line: 5,
      payload: {
        title: 'Workshop details',
        items: [
          { label: 'Date', value: 'August 15, 2026' },
          { label: 'Time', value: '19:30–21:30' },
          { label: 'Format', value: 'Open English workshop' },
        ],
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## What will happen in the room\n\nWe will begin by watching one ordinary experience become a clear three-part story. Participants will then choose a moment of their own and test it in a small group.\n',
      line: 15,
    },
    {
      kind: 'directive',
      name: 'timeline',
      line: 20,
      payload: {
        title: 'The evening plan',
        items: [
          {
            label: '19:30',
            title: 'See the structure',
            description:
              'A facilitator demonstrates how a moment becomes a story.',
          },
          {
            label: '20:00',
            title: 'Build your own version',
            description:
              'Participants identify the change, the detail, and the next beat.',
          },
          {
            label: '20:45',
            title: 'Tell it and receive feedback',
            description:
              'Small groups listen for clarity, movement, and one memorable image.',
          },
        ],
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## Who should come\n\nCome if you want to make a presentation less abstract, explain a project more clearly, or become more comfortable speaking without a complete script.\n\n- New speakers are welcome.\n- Experienced members can bring a current speech idea.\n- Guests may participate or simply observe.\n',
      line: 33,
    },
    {
      kind: 'directive',
      name: 'video',
      line: 42,
      payload: {
        media: 'V01',
        caption:
          'A short look at the supportive practice format used in SoarHigh workshops',
      },
    },
    {
      kind: 'directive',
      name: 'takeaway',
      line: 47,
      payload: {
        title: 'Bring one moment, not a finished speech',
        text: 'Choose an experience that changed what you noticed, decided, or did. We will help you shape the rest in the room.',
      },
    },
    {
      kind: 'markdown',
      source:
        '\nSeats are limited so that every participant has time to practice. ==Reserve a place, bring one real moment, and leave with a story you can keep developing.==',
      line: 51,
    },
  ],
  media: [
    {
      id: 'M01',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/workshop.jpg?x-oss-process=image/format,webp',
      description:
        'Members practice and compare notes during an interactive workshop.',
      credit: 'SoarHigh Toastmasters',
      people: ['Workshop participants'],
      include: true,
      order: 0,
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
        'A short fixture video representing the workshop practice format.',
      credit: 'Renderer fixture video',
      people: ['Workshop participants'],
      include: true,
      order: 1,
      descriptionSource: 'user',
      descriptionStatus: 'confirmed',
    },
  ],
  coverMediaId: 'M01',
  presentation: {
    layout: 'brand-default',
    palette: 'brand-blue',
    appearance: 'light',
    typeface: 'modern-sans',
  },
};
