// usePermission(): permission checks for the signed-in role, read from the matrix in permissions.js.
// Hiding a button is a convenience only; the backend must still reject the request.
import { createContext, useContext, useMemo } from 'react';
import { can } from './permissions.js';

// The context value is the role string itself, so consumers re-render only when the role changes.
export const RbacContext = createContext(null);

export function usePermission() {
  const role = useContext(RbacContext);
  return useMemo(() => ({ role, can: (screenKey, action) => can(role, screenKey, action) }), [role]);
}
