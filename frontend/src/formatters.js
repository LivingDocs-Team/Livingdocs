/** "PENDING_STAFF_REVIEW" -> "pending staff review". */
export function words(value) {
  return String(value || '').replace(/_/g, ' ').toLowerCase();
}

export function formatTime(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : 'Unknown time';
}
