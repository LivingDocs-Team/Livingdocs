// TODO: thay bằng screen flow chính thức của nhóm
// PROVISIONAL flow for Administrator. The team has not provided this flow yet, so it is built only
// from the matrix rows where Administrator has a permission, grouped into modules. Every screen is a
// placeholder except Profile: the existing Repository Management page also shows pull requests and
// commits (#7), which Administrator may not read, so it is not wired here.
import { module, placeholder, profileSettings } from './nodes.js';

export default Object.freeze({
  role: 'ADMINISTRATOR',
  provisional: true,
  landing: '/account/profile',
  modules: Object.freeze([
    module('account', 'Account Management', [
      profileSettings(),
    ]),
    module('repositories', 'Repositories', [
      placeholder('repository-management', 'Repository Management & Synchronization', '/admin/repositories', 'repositories'), // #6
    ]),
    module('administration', 'Administration', [
      placeholder('user-management', 'Users, Roles & Permissions', '/admin/users', 'userManagement'), // #24
      placeholder('workspace-administration', 'Workspace & Repository Administration', '/admin/workspaces', 'workspaceAdministration'), // #25
      placeholder('system-configuration', 'System Configuration', '/admin/configuration', 'systemConfiguration'), // #26
      placeholder('notification-policies', 'Notification Policies', '/admin/notification-policies', 'notificationPolicies'), // #28
    ]),
    module('monitoring', 'Monitoring & Audit', [
      placeholder('monitoring', 'Monitoring, Audit Logs & Analytics', '/admin/monitoring', 'monitoring'), // #27
      placeholder('approval-audit', 'Approval Audit Trail & History', '/admin/approval-audit', 'approvalAudit'), // #13
    ]),
  ]),
});
