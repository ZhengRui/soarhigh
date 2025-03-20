import {
  MeetingIF,
  SegmentIF,
  CategoryCandidatesIF,
  VoteRecordIF,
} from '@/interfaces';
import { requestTemplate, responseHandlerTemplate } from './requestTemplate';
import {
  SAASegment,
  TOMIntroSegment,
  TTMOpeningSegment,
  GuestsIntroSegment,
  TimerIntroSegment,
  GrammarianIntroSegment,
  HarkMasterIntroSegment,
  dummyParams,
} from './defaultSegments';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * Get votes for a meeting
 * @param meetingId The ID of the meeting
 * @returns Vote form data
 */
const getVotesCore = requestTemplate(
  (meetingId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/votes`,
    method: 'GET',
    headers: new Headers({ Accept: 'application/json' }),
  }),
  responseHandlerTemplate,
  null,
  true,
  true // soft auth - backend allows public access
);

export const getVotes = async (
  meetingId: string,
  addMissingCategories: boolean = false
) => {
  const result = await getVotesCore(meetingId);
  if (result.length > 0) {
    // make sure the seven core categories are present
    const defaultCategories = [
      'Best Prepared Speaker',
      'Best Host',
      'Best Table Topic Speaker',
      'Best Facilitator',
      'Best Evaluator',
      'Best Supporter',
      'Best Meeting Manager',
    ];

    // add any missing categories
    if (addMissingCategories) {
      const missingCategories = defaultCategories.filter(
        (category) =>
          !result.some((r: CategoryCandidatesIF) => r.category === category)
      );
      result.push(
        ...missingCategories.map((category) => ({ category, candidates: [] }))
      );
    }

    // sort the result by category using the order of defaultCategories
    // if the category is not in defaultCategories, move it to the end
    result.sort((a: CategoryCandidatesIF, b: CategoryCandidatesIF) => {
      const aIndex = defaultCategories.indexOf(a.category);
      const bIndex = defaultCategories.indexOf(b.category);

      if (aIndex === -1 && bIndex === -1) return 0;
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });
  }
  return result;
};

/**
 * Get vote status for a meeting
 * @param meetingId The ID of the meeting
 * @returns Vote status information
 */
export const getVoteStatus = requestTemplate(
  (meetingId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/votes/status`,
    method: 'GET',
    headers: new Headers({ Accept: 'application/json' }),
  }),
  responseHandlerTemplate,
  null,
  true,
  true // soft auth - backend allows public access
);

/**
 * Save voting form configuration for a meeting
 * @param meetingId The ID of the meeting
 * @param categories Vote categories and candidates
 * @returns Success message
 */
export const saveVoteForm = requestTemplate(
  (meetingId: string, categories: CategoryCandidatesIF[]) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/votes/form`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ votes: categories }),
  }),
  responseHandlerTemplate,
  null,
  true
);

/**
 * Update vote status for a meeting
 * @param meetingId The ID of the meeting
 * @param isOpen Whether voting is open
 * @returns Success message
 */
export const updateVoteStatus = requestTemplate(
  (meetingId: string, open: boolean) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/votes/status`,
    method: 'PUT',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ open }),
  }),
  responseHandlerTemplate,
  null,
  true
);

/**
 * Cast votes for a meeting
 * @param meetingId The ID of the meeting
 * @param votes Array of votes
 * @returns Success message
 */
export const castVotes = requestTemplate(
  (meetingId: string, votes: VoteRecordIF[]) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/vote`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ votes }),
  }),
  responseHandlerTemplate,
  null,
  false
);

/**
 * Extract candidates from meeting segments based on roles
 * @param meeting The meeting object containing segments
 * @returns Array of category candidates
 */
export const extractCandidatesFromMeeting = (
  meeting: MeetingIF
): CategoryCandidatesIF[] => {
  // Initialize with all core categories (empty candidates arrays)
  const voteForm: CategoryCandidatesIF[] = [
    { category: 'Best Prepared Speaker', candidates: [] },
    { category: 'Best Host', candidates: [] },
    { category: 'Best Table Topic Speaker', candidates: [] }, // Will be manually populated
    { category: 'Best Facilitator', candidates: [] },
    { category: 'Best Evaluator', candidates: [] },
    { category: 'Best Supporter', candidates: [] },
    { category: 'Best Meeting Manager', candidates: [] },
  ];

  // Helper function to add a candidate to a category
  const addCandidate = (
    categoryName: string,
    name: string,
    segment?: string
  ) => {
    const category = voteForm.find((cat) => cat.category === categoryName);
    if (category && name && !category.candidates.some((c) => c.name === name)) {
      category.candidates.push({ name, segment, count: 0 });
    }
  };

  meeting.segments.forEach((segment: SegmentIF) => {
    // Skip segments without role takers
    if (!segment.role_taker) return;

    const roleTaker = segment.role_taker;

    // If the role taker doesn't have a member_id, they're a guest - add to supporters
    if (
      roleTaker.name &&
      (!roleTaker.member_id || roleTaker.member_id.trim() === '')
    ) {
      addCandidate('Best Supporter', roleTaker.name, segment.type);
    }

    // Determine category based on segment type
    let category: string | null = null;

    // Best Prepared Speaker
    if (
      segment.type.startsWith('Prepared Speech') &&
      !segment.type.includes('Evaluation')
    ) {
      category = 'Best Prepared Speaker';
    }
    // Best Host
    else if (
      segment.type === new TOMIntroSegment(dummyParams).type || // TOM Introduction
      segment.type === new TTMOpeningSegment(dummyParams).type || // TTM Opening
      segment.type === new GuestsIntroSegment(dummyParams).type // Guests Self Introduction
    ) {
      category = 'Best Host';
    }
    // Best Evaluator
    else if (segment.type.includes('Evaluation')) {
      category = 'Best Evaluator';
    }
    // Best Facilitator
    else if (
      segment.type === new SAASegment(dummyParams).type || // SAA
      segment.type === new TimerIntroSegment(dummyParams).type || // Timer
      segment.type === new GrammarianIntroSegment(dummyParams).type || // Grammarian
      segment.type === new HarkMasterIntroSegment(dummyParams).type // Hark Master
    ) {
      category = 'Best Facilitator';
    }

    // Add candidate to the appropriate category
    if (category && roleTaker.name) {
      addCandidate(category, roleTaker.name, segment.type);
    }
  });

  // Add meeting manager to Best Meeting Manager category if exists
  if (meeting.manager && meeting.manager.name) {
    addCandidate(
      'Best Meeting Manager',
      meeting.manager.name,
      'Meeting Manager'
    );
  }

  return voteForm;
};
