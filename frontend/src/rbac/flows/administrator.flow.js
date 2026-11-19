// TODO: thay bằng screen flow chính thức của nhóm
// PROVISIONAL flow for Administrator. The team has not provided this flow yet, so it is built only
// from the matrix rows where Administrator has a permission, grouped into modules. The Administration and
// Monitoring screens (#24-#28) open the Administration dashboard (LD-316); every other screen is a
// placeholder except Profile: the existing Repository Management page also shows pull requests and
// commits (#7), which Administrator may not read, so it is not wired here.
import { implemented, module, placeholder, profileSettings } from './nodes.js';

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
      implemented('user-management', 'Users, Roles & Permissions', '/admin/users', 'userManagement', 'AdminDashboard'), // #24
      implemented('workspace-administration', 'Workspace & Repository Administration', '/admin/workspaces', 'workspaceAdministration', 'AdminDashboard'), // #25
      implemented('system-configuration', 'System Configuration', '/admin/configuration', 'systemConfiguration', 'AdminDashboard'), // #26
      implemented('notification-policies', 'Notification Policies', '/admin/notification-policies', 'notificationPolicies', 'AdminDashboard'), // #28
    ]),
    module('monitoring', 'Monitoring & Audit', [
      implemented('monitoring', 'Monitoring, Audit Logs & Analytics', '/admin/monitoring', 'monitoring', 'AdminDashboard'), // #27
      placeholder('approval-audit', 'Approval Audit Trail & History', '/admin/approval-audit', 'approvalAudit'), // #13
    ]),
  ]),
});
