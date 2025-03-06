interface NextWednesdayResult {
  date: string; // yyyy-MM-dd format
  display: string; // "This Wednesday" or "Next Wednesday"
}

export const getNextWednesday = (): NextWednesdayResult => {
  const today = new Date();
  const day = today.getDay(); // 0 is Sunday, 3 is Wednesday
  let daysUntilWednesday = (3 - day + 7) % 7;

  // If it's Wednesday but after 7 PM, show next Wednesday
  if (daysUntilWednesday === 0 && today.getHours() >= 19) {
    daysUntilWednesday = 7;
  }

  const nextWednesday = new Date(today);
  nextWednesday.setDate(today.getDate() + daysUntilWednesday);

  return {
    date: nextWednesday.toISOString().split('T')[0], // yyyy-MM-dd format
    display: daysUntilWednesday === 0 ? 'This Wednesday' : 'Next Wednesday',
  };
};

/**
 * Converts a human-readable date string like "Nov. 6, 2024 (Wed)" to ISO format "2024-11-06"
 * @param dateString The human-readable date string to convert
 * @returns ISO formatted date string (YYYY-MM-DD) or the original string if parsing fails
 */
export const convertHumanReadableDateToISO = (dateString: string): string => {
  try {
    // Try to match the common format from OCR: "Month Day, Year (Weekday)"
    const regex = /([A-Za-z]+)\.*\s+(\d{1,2}),?\s+(\d{4})/;
    const match = dateString.match(regex);

    if (!match) {
      // If the string is already in ISO format, return it
      if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
        return dateString;
      }
      // If we can't parse it, return the original
      return dateString;
    }

    const monthStr = match[1];
    const day = parseInt(match[2], 10);
    const year = parseInt(match[3], 10);

    // Map month names to month numbers (0-based)
    const months: Record<string, number> = {
      jan: 0,
      january: 0,
      feb: 1,
      february: 1,
      mar: 2,
      march: 2,
      apr: 3,
      april: 3,
      may: 4,
      jun: 5,
      june: 5,
      jul: 6,
      july: 6,
      aug: 7,
      august: 7,
      sep: 8,
      september: 8,
      oct: 9,
      october: 9,
      nov: 10,
      november: 10,
      dec: 11,
      december: 11,
    };

    // Get month number from map, case insensitive
    const monthLower = monthStr.toLowerCase();
    const monthNum = months[monthLower];

    if (monthNum === undefined || isNaN(day) || isNaN(year)) {
      return dateString; // Return original if any part couldn't be parsed
    }

    // Fix for timezone issues: Use UTC methods to avoid date shifting
    // Format as YYYY-MM-DD (ISO format) using string manipulation to avoid timezone issues
    const month = monthNum + 1; // Convert 0-based month to 1-based
    return `${year}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
  } catch (error) {
    console.error('Error parsing date:', error);
    return dateString; // Return original if any error occurs
  }
};
