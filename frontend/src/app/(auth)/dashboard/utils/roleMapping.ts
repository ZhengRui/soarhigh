// Role mapping from segment types to matrix display labels
// Using EXACT match only for the specific roles picked by user

export const MATRIX_ROLES = [
  {
    key: 'SAA',
    label: 'SAA',
    pattern: 'Meeting Rules Introduction (SAA)',
  },
  {
    key: 'President',
    label: 'President',
    pattern: 'Opening Remarks (President)',
  },
  {
    key: 'TOM',
    label: 'TOM',
    pattern: 'TOM (Toastmaster of Meeting) Introduction',
  },
  {
    key: 'Timer',
    label: 'Timer',
    pattern: 'Timer',
  },
  {
    key: 'Grammarian',
    label: 'Grammarian',
    pattern: 'Grammarian',
  },
  {
    key: 'HarkMaster',
    label: 'Hark Master',
    pattern: 'Hark Master',
  },
  {
    key: 'GuestIntroHost',
    label: 'Guest Intro Host',
    pattern: 'Guests Self Introduction (30s per guest)',
  },
  {
    key: 'TTM',
    label: 'TTM',
    pattern: 'TTM (Table Topic Master) Opening',
  },
  {
    key: 'PreparedSpeech',
    label: 'Prepared Speech',
    pattern: /^Prepared Speech(?:\s+\d+)?$/,
  },
  {
    key: 'TTE',
    label: 'TTE',
    pattern: 'Table Topic Evaluation',
  },
  {
    key: 'IE',
    label: 'IE',
    pattern: /^Prepared Speech(?:\s+\d+)?\s+Evaluation$/,
  },
  {
    key: 'GE',
    label: 'GE',
    pattern: 'General Evaluation',
  },
  {
    key: 'MoT',
    label: 'MoT',
    pattern: 'Moment of Truth',
  },
  {
    key: 'WorkshopSpeaker',
    label: 'Workshop Speaker',
    pattern: 'Workshop',
  },
] as const;

export type MatrixRoleKey = (typeof MATRIX_ROLES)[number]['key'];

export function normalizeRoleToMatrixKey(
  segmentType: string
): MatrixRoleKey | null {
  const trimmed = segmentType.trim();

  for (const role of MATRIX_ROLES) {
    const { pattern } = role;
    if (typeof pattern === 'string') {
      // Exact match only
      if (trimmed === pattern) {
        return role.key;
      }
    } else {
      // Regex pattern for Prepared Speech variations
      if (pattern.test(trimmed)) {
        return role.key;
      }
    }
  }

  return null;
}
