import type { WePostRenderDocument } from '../types';

export const memberStoryFixture: WePostRenderDocument = {
  schemaVersion: 1,
  renderVersion: 1,
  title: 'Finding Her Voice Between the Prepared Lines',
  slug: 'finding-her-voice-between-the-prepared-lines',
  excerpt:
    'How one member moved from memorizing every sentence to trusting the story she wanted to tell.',
  byline: 'SoarHigh Toastmasters Editorial Team',
  articleType: 'member-story',
  body: [
    {
      kind: 'markdown',
      source:
        'Elena used to prepare for a speech by writing every sentence, every pause, and every gesture. The page made her feel safe until she looked away from it.\n\nHer change did not arrive as a sudden burst of confidence. It began with one meeting where she forgot a line and discovered that the audience was still with her.\n',
      line: 1,
    },
    {
      kind: 'directive',
      name: 'person',
      line: 5,
      payload: {
        name: 'Elena Zhou',
        role: 'SoarHigh member and Pathways mentor',
        media: 'M01',
        summary:
          'Elena joined the club to become more comfortable speaking at work. She stayed because the meetings gave her a place to experiment without pretending to be finished.',
        quote:
          'The audience did not need my exact sentence. They needed me to stay with the story.',
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## A quieter beginning\n\nDuring her first months, Elena measured a good speech by how closely it matched the script. A missed phrase felt like evidence that she was not ready.\n\nHer mentor suggested a different practice: prepare three turning points instead of thirty perfect sentences. ==The goal was no longer to remember the page; it was to remember where the story was going.==\n',
      line: 12,
    },
    {
      kind: 'directive',
      name: 'pull-quote',
      line: 19,
      payload: {
        text: 'When I stopped chasing the missing sentence, I could finally notice the people listening.',
        attribution: 'Elena Zhou',
      },
    },
    {
      kind: 'markdown',
      source:
        '\n## Practice changed what confidence meant\n\nThe next speeches were not flawless. They contained pauses, substitutions, and moments of visible thought. They also sounded more like Elena.\n\nShe began using the same approach in project updates at work: know the destination, make eye contact, and allow the exact language to arrive in the room.\n',
      line: 23,
    },
    {
      kind: 'directive',
      name: 'gallery',
      line: 30,
      payload: {
        items: ['M02', 'M03'],
        caption:
          'Elena speaking, listening to feedback, and mentoring another member',
      },
    },
    {
      kind: 'directive',
      name: 'takeaway',
      line: 37,
      payload: {
        title: 'Confidence can be a way of recovering',
        text: 'Prepare the idea deeply enough that one forgotten sentence cannot take the whole story away.',
      },
    },
    {
      kind: 'markdown',
      source:
        '\nElena still writes before important talks. The difference is that the page now supports her voice instead of replacing it. ==Preparation gives her somewhere to begin, not somewhere she must remain.==',
      line: 41,
    },
  ],
  media: [
    {
      id: 'M01',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/competition.jpg?x-oss-process=image/format,webp',
      description:
        'Elena smiles after finishing a speech in front of the club.',
      credit: 'SoarHigh Toastmasters',
      people: ['Elena Zhou'],
      include: true,
      order: 0,
      descriptionSource: 'user',
      descriptionStatus: 'confirmed',
    },
    {
      id: 'M02',
      kind: 'image',
      sourceUrl:
        'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/weeklymeeting.jpg?x-oss-process=image/format,webp',
      description:
        'A club member practices a speech while the audience listens.',
      credit: 'SoarHigh Toastmasters',
      people: ['Elena Zhou', 'Club members'],
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
        'Members exchange specific feedback after a prepared speech.',
      credit: 'SoarHigh Toastmasters',
      people: ['Club members'],
      include: true,
      order: 2,
      descriptionSource: 'ai',
      descriptionStatus: 'confirmed',
    },
  ],
  coverMediaId: 'M01',
  presentation: {
    layout: 'editorial-feature',
    palette: 'warm-terracotta',
    appearance: 'light',
    typeface: 'humanist-mix',
  },
};
