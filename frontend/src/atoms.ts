import { atom } from 'jotai';
import { PaginatedMeetings } from '@/interfaces';

// Interface for our global meetings state
export interface MeetingsState {
  pages: Record<number, PaginatedMeetings>;
}

// Initial empty state
const initialState: MeetingsState = {
  pages: {},
};

// Main atom for storing all paginated meetings data
export const meetingsAtom = atom<MeetingsState>(initialState);
