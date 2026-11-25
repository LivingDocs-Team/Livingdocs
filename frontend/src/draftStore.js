// Drafts and versions the user creates on the Generated Documentation page. They are kept in this browser
// (localStorage) so a reload does not lose them; they are not shared with other devices or submitted.
const PREFIX = 'livingdocs.drafts.';

function keyFor(userId, docKey) {
  return `${PREFIX}${userId}.${docKey}`;
}

export function loadDraft(userId, docKey) {
  if (!userId || !docKey) return null;
  try {
    const raw = window.localStorage.getItem(keyFor(userId, docKey));
    if (!raw) return null;
    const value = JSON.parse(raw);
    return {
      draft: typeof value.draft === 'string' ? value.draft : '',
      versions: Array.isArray(value.versions) ? value.versions.filter((item) => item && typeof item.content === 'string') : [],
    };
  } catch {
    return null;
  }
}

export function saveDraft(userId, docKey, patch) {
  if (!userId || !docKey) return false;
  try {
    const current = loadDraft(userId, docKey) || { draft: '', versions: [] };
    window.localStorage.setItem(keyFor(userId, docKey), JSON.stringify({ ...current, ...patch }));
    return true;
  } catch {
    return false;
  }
}
