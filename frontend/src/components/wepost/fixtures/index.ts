import { eventPreviewFixture } from './eventPreview';
import { meetingRecapFixture } from './meetingRecap';
import { memberStoryFixture } from './memberStory';

export const WEPOST_FIXTURES = {
  'meeting-recap': meetingRecapFixture,
  'member-story': memberStoryFixture,
  'event-preview': eventPreviewFixture,
} as const;

export type WePostFixtureId = keyof typeof WEPOST_FIXTURES;

export const WEPOST_FIXTURE_CONTEXT_LABELS: Record<WePostFixtureId, string> = {
  'meeting-recap': 'Meeting 236',
  'member-story': 'Member since 2024',
  'event-preview': 'Open Workshop',
};

export const WEPOST_FIXTURE_IDS = Object.keys(
  WEPOST_FIXTURES
) as WePostFixtureId[];
