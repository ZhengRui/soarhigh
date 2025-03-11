import { useMemo } from 'react';
import { CategoryCandidatesIF } from '@/interfaces';
import { extractCandidatesFromMeeting } from '@/utils/votes';
import { useMeeting } from '../useMeeting';

/**
 * Hook to get default vote form from a meeting
 * @param meetingId The meeting ID
 * @returns Array of default vote form
 */
export function useDefaultVoteForm(meetingId: string) {
  const { data: meeting, isLoading } = useMeeting(meetingId);

  const defaultVoteForm = useMemo<CategoryCandidatesIF[]>(() => {
    if (!meeting) return [];
    return extractCandidatesFromMeeting(meeting);
  }, [meeting]);

  return {
    defaultVoteForm,
    isLoading,
  };
}
