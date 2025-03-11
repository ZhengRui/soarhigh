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
} from '../app/(auth)/meetings/default';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * Get votes for a meeting
 * @param meetingId The ID of the meeting
 * @param asForm Whether to return form-structured data (categories and candidates) instead of full vote data
 * @returns An array of votes or form-structured data depending on asForm parameter
 */
export const getVotes = requestTemplate(
  (meetingId: string, asForm: boolean = false) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/votes${asForm ? '?as_form=true' : ''}`,
    method: 'GET',
    headers: new Headers({ Accept: 'application/json' }),
  }),
  responseHandlerTemplate,
  null,
  true,
  true // soft auth - backend allows public access
);

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
    body: JSON.stringify({ categories }),
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
  (meetingId: string, isOpen: boolean) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/votes/status`,
    method: 'PUT',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ is_open: isOpen }),
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
  const addCandidate = (categoryName: string, candidateName: string) => {
    const category = voteForm.find((cat) => cat.category === categoryName);
    if (
      category &&
      candidateName &&
      !category.candidates.includes(candidateName)
    ) {
      category.candidates.push(candidateName);
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
      addCandidate('Best Supporter', roleTaker.name);
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
      addCandidate(category, roleTaker.name);
    }
  });

  // Add meeting manager to Best Meeting Manager category if exists
  if (meeting.manager && meeting.manager.name) {
    addCandidate('Best Meeting Manager', meeting.manager.name);
  }

  return voteForm;
};
