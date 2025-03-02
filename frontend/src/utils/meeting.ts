import { MeetingIF } from '../interfaces';
import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * Creates a new meeting with draft status
 * @param meetingData The meeting data to be saved
 * @returns The created meeting with its ID
 */
export const createMeeting = requestTemplate(
  (meetingData: MeetingIF) => ({
    url: `${apiEndpoint}/meetings`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify(meetingData),
  }),
  responseHandlerTemplate,
  null,
  true // Requires authentication
);

/**
 * Fetches all meetings
 * @returns List of all meetings the user has access to
 * (all published meetings for everyone, draft meetings only for members)
 */
export const getMeetings = requestTemplate(
  () => ({
    url: `${apiEndpoint}/meetings`,
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  true, // Requires authentication
  true // Soft authentication
);

/**
 * Fetches a specific meeting by ID
 * @param meetingId The ID of the meeting to fetch
 * @returns The meeting data
 */
export const getMeetingById = requestTemplate(
  (meetingId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}`,
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  true, // Requires authentication
  true // Soft authentication
);

/**
 * Updates an existing meeting
 * @param meetingId The ID of the meeting to update
 * @param meetingData The updated meeting data
 * @returns The updated meeting
 */
export const updateMeeting = requestTemplate(
  (meetingId: string, meetingData: Partial<MeetingIF>) => ({
    url: `${apiEndpoint}/meetings/${meetingId}`,
    method: 'PUT',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify(meetingData),
  }),
  responseHandlerTemplate,
  null,
  true // Requires authentication
);

/**
 * Updates just the status of a meeting (publish/unpublish)
 * @param meetingId The ID of the meeting to update
 * @param status The new status ('draft' or 'published')
 * @returns The updated meeting
 */
export const updateMeetingStatus = requestTemplate(
  (meetingId: string, status: 'draft' | 'published') => ({
    url: `${apiEndpoint}/meetings/${meetingId}/status`,
    method: 'PUT',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ status }),
  }),
  responseHandlerTemplate,
  null,
  true // Requires authentication
);

/**
 * Deletes a meeting
 * @param meetingId The ID of the meeting to delete
 * @returns Success confirmation
 */
export const deleteMeeting = requestTemplate(
  (meetingId: string) => ({
    url: `${apiEndpoint}/meetings/${meetingId}`,
    method: 'DELETE',
  }),
  responseHandlerTemplate,
  null,
  true // Requires authentication
);
