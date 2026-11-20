// Route guard: decides what to show for a path. Pure function, shared by App.jsx and the tests.
// It only reads screenFlows and the permission matrix, so a new screen needs config changes only.
import { findScreen, isInternalPath, landingPath } from './flows/index.js';
import { canAccess } from './permissions.js';
import { normalizeRole } from './roles.js';

// Screen 1 (before sign-in). Register only creates Developer accounts (the backend assigns DEVELOPER).
export const PUBLIC_ROUTES = Object.freeze({
  '/': 'home',
  '/login': 'login',
  '/register': 'register',
});

export function normalizePath(path) {
  if (typeof path !== 'string' || path === '') return '/';
  const withSlash = path.startsWith('/') ? path : `/${path}`;
  return withSlash.length > 1 ? withSlash.replace(/\/+$/, '') : withSlash;
}

/**
 * @returns one of
 *  { kind: 'public', page: 'home' | 'login' | 'register' }
 *  { kind: 'redirect', to }                       -- caller replaces the URL
 *  { kind: 'screen', node, trail }                 -- allowed internal screen
 *  { kind: 'forbidden' }                           -- internal screen the role may not open
 *  { kind: 'no-role' }                             -- signed in, but the account has no known role
 */
export function resolveRoute({ path, role, isAuthenticated }) {
  const current = normalizePath(path);
  const publicPage = PUBLIC_ROUTES[current];

  if (!isAuthenticated) {
    return publicPage ? { kind: 'public', page: publicPage } : { kind: 'redirect', to: '/login' };
  }

  const normalizedRole = normalizeRole(role);
  if (!normalizedRole) return { kind: 'no-role' };

  const landing = landingPath(normalizedRole);
  if (publicPage) return { kind: 'redirect', to: landing };

  const match = findScreen(normalizedRole, current);
  if (match && canAccess(normalizedRole, match.node.permissionKey)) {
    return { kind: 'screen', node: match.node, trail: match.trail };
  }
  if (match || isInternalPath(current)) return { kind: 'forbidden' };
  return { kind: 'redirect', to: landing };
}

/** Where to go right after sign-in: the requested internal page when allowed, otherwise the landing page. */
export function postLoginPath(role, requestedPath) {
  if (requestedPath) {
    const decision = resolveRoute({ path: requestedPath, role, isAuthenticated: true });
    if (decision.kind === 'screen') return normalizePath(requestedPath);
  }
  return landingPath(role);
}
