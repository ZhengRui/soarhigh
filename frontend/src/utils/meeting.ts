import { MeetingIF } from '../interfaces';
import {
  requestTemplate,
  responseHandlerTemplate,
  formConstructor,
} from './requestTemplate';

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
 * @param options Pagination and filter options
 * @returns Paginated list of meetings the user has access to
 */
export const getMeetings = requestTemplate(
  (options: { page?: number; page_size?: number; status?: string } = {}) => {
    // Apply default values
    const page = options.page || 1;
    const page_size = options.page_size || 10;

    // Construct URL with query parameters
    let url = `${apiEndpoint}/meetings?page=${page}&page_size=${page_size}`;

    // Add status parameter if provided
    if (options.status) {
      url += `&status=${options.status}`;
    }

    return {
      url,
      method: 'GET',
    };
  },
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

/**
 * Saves awards for a meeting
 * @param meetingId The ID of the meeting to save awards for
 * @param awards The awards data to save
 * @returns The saved awards
 */
export const saveMeetingAwards = requestTemplate(
  (meetingId: string, awards: any[]) => ({
    url: `${apiEndpoint}/meetings/${meetingId}/awards`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify({ awards }),
  }),
  responseHandlerTemplate,
  null,
  true // Requires authentication
);

/**
 * Parses a meeting from an uploaded agenda image
 * @param imageFile The image file to be processed
 * @returns The parsed meeting data
 */
export const parseMeetingFromImage = requestTemplate(
  (imageFile: File) => {
    const formData = formConstructor({ image: imageFile });
    return {
      url: `${apiEndpoint}/meeting/parse_agenda_image`,
      method: 'POST',
      body: formData,
    };
  },
  responseHandlerTemplate,
  null,
  true // Requires authentication
);
