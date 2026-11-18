// Screen 2 (signed in): sidebar and breadcrumb rendered from the role's screen flow, and the
// current screen rendered from the registry below. No role-specific if/else lives here.
import DocumentationCollections from '../DocumentationCollections';
import DocumentationManagement from '../DocumentationManagement';
import DocumentationSearch from '../DocumentationSearch';
import GitHubConnection from '../GitHubConnection';
import ManagerApprovalQueue from '../ManagerApprovalQueue';
import NotificationPreferences from '../NotificationPreferences';
import Profile from '../Profile';
import RepositoryManagement from '../RepositoryManagement';
import StaffReviewQueue from '../StaffReviewQueue';
import TemplateLibrary from '../TemplateLibrary';
import Icon from '../icons';
import { RBAC_UI } from './config.js';
import { getFlow } from './flows/index.js';
import ForbiddenScreen from './ForbiddenScreen';
import { hrefFor } from './hashRoute.js';
import PageFrame from './PageFrame';
import PlaceholderScreen from './PlaceholderScreen';
import { ROLE_LABELS } from './roles.js';

// What each Profile & Settings section offers, shown on its tile.
const CHILD_HINTS = {
  profile: 'Your name, username and email.',
  'notification-preferences': 'Choose which messages you receive.',
};

function ChildIndex({ node }) {
  return (
    <PageFrame title={node.label} titleId="rbac-child-index-title" subtitle="Choose a section." className="shell-bare">
      <div className="tiles">
        {node.children.map((child) => (
          <a key={child.key} className="tile fx" href={hrefFor(child.path)}>
            <b>{child.label}</b>
            <small>{CHILD_HINTS[child.key] || ''}</small>
            <span className="tile-go">Open <Icon name="arrow" size={13} /></span>
          </a>
        ))}
      </div>
    </PageFrame>
  );
}

// Screen registry: flow nodes name a component; add new screens here once they are built.
// `framed` panels were designed to sit inside the Documentation Management page, so the shell gives
// them a page frame titled with their module.
const SCREENS = {
  ChildIndex: { Component: ChildIndex },
  Profile: { Component: Profile },
  NotificationPreferences: { Component: NotificationPreferences },
  GitHubConnection: { Component: GitHubConnection },
  RepositoryManagement: { Component: RepositoryManagement },
  DocumentationCollections: { Component: DocumentationCollections },
  DocumentationManagement: { Component: DocumentationManagement },
  DocumentationSearch: { Component: DocumentationSearch },
  TemplateLibrary: { Component: TemplateLibrary },
  StaffReviewQueue: { Component: StaffReviewQueue, framed: true },
  ManagerApprovalQueue: { Component: ManagerApprovalQueue, framed: true },
};

// Sub-screens that are only a part of their parent's page open that page. A sub-screen backed by a
// different component (Staff > Document Editor) is a page of its own, so the parent offers it in its header.
function ownPageLinks(node) {
  return node.children.filter((child) => child.status === 'implemented' && child.component !== node.component);
}

function renderScreen(node, trail, userId) {
  const entry = node.status === 'implemented' ? SCREENS[node.component] : null;
  if (!entry) return <PlaceholderScreen node={node} trail={trail} />;
  const screen = <entry.Component userId={userId} node={node} />;
  if (!entry.framed) return screen;
  const links = ownPageLinks(node);
  const actions = links.length > 0 && links.map((child) => (
    <a key={child.key} className="page-action" href={hrefFor(child.path)}>{child.label}</a>
  ));
  return <PageFrame title={trail[0].label} className="documentation-page" actions={actions}>{screen}</PageFrame>;
}

// The menu lists the main screens only. A parent stays highlighted while one of its sub-screens is open.
function isActive(node, activePath) {
  return node.path === activePath || node.children.some((child) => isActive(child, activePath));
}

function MenuList({ nodes, activePath }) {
  return (
    <ul className="app-sidebar-list">
      {nodes.map((node) => {
        const dimmed = node.status === 'placeholder' && RBAC_UI.dimPlaceholders;
        return (
          <li key={node.key}>
            <a
              href={hrefFor(node.path)}
              className={`app-sidebar-link${dimmed ? ' is-placeholder' : ''}`}
              aria-current={isActive(node, activePath) ? 'page' : undefined}
              data-status={node.status}
              title={dimmed ? 'Chưa triển khai' : undefined}
            >
              {node.label}
            </a>
          </li>
        );
      })}
    </ul>
  );
}

function Breadcrumb({ trail }) {
  return (
    <nav className="app-breadcrumb" aria-label="Breadcrumb">
      <ol>
        {trail.map((item, index) => {
          const isLast = index === trail.length - 1;
          return (
            <li key={item.key}>
              {item.type === 'screen' && !isLast
                ? <a href={hrefFor(item.path)}>{item.label}</a>
                : <span aria-current={isLast ? 'page' : undefined}>{item.label}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default function AppShell({ decision, userId, userRole, userEmail, notice, onLogout, logoutError }) {
  const flow = getFlow(userRole);
  const activePath = decision.kind === 'screen' ? decision.node.path : null;

  // Remount (and replay the entrance) when the screen changes, not when only a sub-section does.
  const screenKey = decision.kind === 'screen' ? (decision.node.component || decision.node.path) : decision.kind;
  let content;
  if (!flow || decision.kind === 'no-role') {
    content = (
      <PageFrame title="No role assigned">
        <p role="alert">Your account has no LivingDocs role. Ask an Administrator to assign one.</p>
      </PageFrame>
    );
  } else if (decision.kind === 'forbidden') {
    content = <ForbiddenScreen landing={flow.landing} />;
  } else if (decision.kind === 'screen') {
    content = renderScreen(decision.node, decision.trail, userId);
  } else {
    content = <p role="status">Loading…</p>;
  }

  return (
    <div className="app app-shell">
      <header className="app-navigation app-shell-header">
        <div className="brand">
          <span className="logo"><Icon name="layers" size={17} /></span>
          LivingDocs
        </div>
        <div className="app-shell-user">
          <span>{userEmail || `User #${userId}`}</span>
          {flow && <strong className="role-pill">{ROLE_LABELS[flow.role]}</strong>}
          {flow?.provisional && (
            <span className="rbac-provisional-badge" title="This role's screen flow is provisional">Provisional flow</span>
          )}
          <button type="button" className="logout-button" onClick={onLogout}>Logout</button>
        </div>
        {logoutError && <p role="alert">{logoutError}</p>}
      </header>
      {notice && <p className="app-shell-notice" role="status">{notice}</p>}

      <div className="app-shell-body">
        {flow && (
          <nav className="app-sidebar" aria-label="Main menu">
            {flow.modules.map((moduleNode) => (
              <section key={moduleNode.key} className="app-sidebar-module" aria-label={moduleNode.label}>
                <p className="app-sidebar-module-label">{moduleNode.label}</p>
                <MenuList nodes={moduleNode.children} activePath={activePath} />
              </section>
            ))}
          </nav>
        )}
        <div className="app-content">
          {decision.kind === 'screen' && <Breadcrumb trail={decision.trail} />}
          <div className="screen-enter" key={screenKey}>{content}</div>
        </div>
      </div>
    </div>
  );
}
