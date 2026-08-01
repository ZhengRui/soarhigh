const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

export function formatWxPostDisplayDate(isoTimestamp: string) {
  const value = new Date(isoTimestamp);
  if (Number.isNaN(value.getTime())) return null;
  return `${MONTHS[value.getUTCMonth()]} ${value.getUTCDate()}, ${value.getUTCFullYear()}`;
}
