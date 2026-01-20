// Heatmap color scale using purple theme (matching existing charts)

export function getHeatmapColor(count: number): string {
  if (count === 0) return 'bg-gray-50';
  if (count === 1) return 'bg-purple-100';
  if (count === 2) return 'bg-purple-200';
  if (count <= 4) return 'bg-purple-300';
  if (count <= 6) return 'bg-purple-400';
  if (count <= 9) return 'bg-purple-500';
  return 'bg-purple-600';
}

export function getHeatmapTextColor(count: number): string {
  // Dark text for light backgrounds, light text for dark backgrounds
  if (count <= 4) return 'text-gray-700';
  return 'text-white';
}
