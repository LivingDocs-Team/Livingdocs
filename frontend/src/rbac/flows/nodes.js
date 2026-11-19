// Helpers that build screen-flow nodes, so every flow file has the same shape:
// module -> screen -> sub-screen. Screens carry key, label, path, permissionKey (a row of
// permissions.js) and status. `component` names an entry of SCREENS in AppShell.jsx.

/** A menu group. Modules have no page of their own. */
export function module(key, label, children) {
  return Object.freeze({ type: 'module', key, label, children: Object.freeze(children) });
}

function screen(key, label, path, permissionKey, component, children) {
  return Object.freeze({
    type: 'screen', key, label, path, permissionKey,
    status: component ? 'implemented' : 'placeholder',
    component,
    // a section() child is part of this screen's page and opens the same component
    children: Object.freeze(children.map((child) => (child.type === 'section'
      ? screen(child.key, child.label, child.path, child.permissionKey, component, [])
      : child))),
  });
}

/** A screen that is backed by an existing component. */
export function implemented(key, label, path, permissionKey, component, children = []) {
  return screen(key, label, path, permissionKey, component, children);
}

/** A screen from the team's flow that is not built yet: it renders the shared "Chưa triển khai" page. */
export function placeholder(key, label, path, permissionKey, children = []) {
  return screen(key, label, path, permissionKey, null, children);
}

/** A sub-screen that is a part of its parent's page (it opens the parent's component). */
export function section(key, label, path, permissionKey) {
  return { type: 'section', key, label, path, permissionKey };
}

/** Account Management > Profile & Settings, shared by every role (matrix row #2). */
export function profileSettings() {
  return implemented('profile-settings', 'Profile & Settings', '/account/profile-settings', 'profile', 'ChildIndex', [
    implemented('profile', 'Profile', '/account/profile', 'profile', 'Profile'),
    implemented('notification-preferences', 'Notification Preferences', '/account/notification-preferences', 'profile', 'NotificationPreferences'),
  ]);
}
