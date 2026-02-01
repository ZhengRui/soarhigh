import { CheckinIF } from '../interfaces';
import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * Fetches all checkins for a meeting
 * Members see all checkins, non-members see only their own
 * @param meetingId The meeting ID
 * @returns List of checkins
 */
export const getCheckins = requestTemplate(
  (meetingId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/checkins`,
    method: 'GET',
    headers: new Headers({
      Accept: 'application/json',
    }),
  }),
  async (response: Response) => {
    const data = await responseHandlerTemplate(response);
    return data.checkins as CheckinIF[];
  },
  null,
  true, // Requires authentication
  true // Soft auth - don't throw if no token
);

/**
 * Resets a segment's checkin (e.g., to release Timer role)
 * Only members can perform this operation
 * @param meetingId The meeting ID
 * @param segmentId The segment ID to reset
 * @returns Result with action taken
 */
export const resetCheckin = requestTemplate(
  (meetingId: string, segmentId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/checkins/reset`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ segment_id: segmentId }),
  }),
  responseHandlerTemplate,
  null,
  true // Requires authentication
);

/**
 * Helper to get checkin for a specific segment
 * @param checkins All checkins
 * @param segmentId The segment ID to find
 * @returns The checkin for this segment or undefined
 */
export function getCheckinForSegment(
  checkins: CheckinIF[] | undefined,
  segmentId: string
): CheckinIF | undefined {
  return checkins?.find((c) => c.segment_id === segmentId);
}
