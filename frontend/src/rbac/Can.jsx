import { usePermission } from './usePermission.js';

/**
 * Renders children only when the signed-in role may perform `action` on `screen`.
 *   <Can screen="templates" action="U"><button>Manage templates</button></Can>
 * Pass a function to disable instead of hide:
 *   <Can screen="staffReview" action="A">{(allowed) => <button disabled={!allowed}>Approve</button>}</Can>
 */
export default function Can({ screen, action, fallback = null, children }) {
  const { can } = usePermission();
  const allowed = can(screen, action);
  if (typeof children === 'function') return children(allowed);
  return allowed ? children : fallback;
}
