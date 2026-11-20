// Roles known to the frontend. Keys match the `role` string returned by /api/auth/me and /api/auth/login;
// their order is the column order of the Screen Authorization matrix.
export const ROLE_LABELS = Object.freeze({
  DEVELOPER: 'Developer',
  STAFF: 'Staff',
  MANAGER: 'Manager',
  TECHNICAL_LEAD: 'Technical Lead',
  ADMINISTRATOR: 'Administrator',
});

export const ROLE_ORDER = Object.freeze(Object.keys(ROLE_LABELS));

// The backend still has a legacy ADMIN role (RoleCatalogInitializer); it is treated as ADMINISTRATOR.
const ALIASES = Object.freeze({ ADMIN: 'ADMINISTRATOR' });

/** Returns a known role name, or null for an empty/unknown role. */
export function normalizeRole(role) {
  if (typeof role !== 'string') return null;
  const upper = role.trim().toUpperCase();
  const resolved = ALIASES[upper] || upper;
  return ROLE_ORDER.includes(resolved) ? resolved : null;
}
