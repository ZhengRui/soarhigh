import { eventPreviewFixture } from './eventPreview';
import { meetingRecapFixture } from './meetingRecap';
import { memberStoryFixture } from './memberStory';

export const WXPOST_FIXTURES = {
  'meeting-recap': meetingRecapFixture,
  'member-story': memberStoryFixture,
  'event-preview': eventPreviewFixture,
} as const;

export type WxPostFixtureId = keyof typeof WXPOST_FIXTURES;

export const WXPOST_FIXTURE_CONTEXT_LABELS: Record<WxPostFixtureId, string> = {
  'meeting-recap': 'Meeting 236',
  'member-story': 'Member since 2024',
  'event-preview': 'Open Workshop',
};

export const WXPOST_FIXTURE_IDS = Object.keys(
  WXPOST_FIXTURES
) as WxPostFixtureId[];
