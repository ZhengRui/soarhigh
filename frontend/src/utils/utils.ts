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
