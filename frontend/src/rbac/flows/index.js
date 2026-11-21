// screenFlows: one tree per role (Role -> Module -> Screen -> Sub-screen).
// The sidebar, breadcrumb and route guard are all derived from these trees.
import { normalizeRole } from '../roles.js';
import administrator from './administrator.flow.js';
import developer from './developer.flow.js';
import manager from './manager.flow.js';
import staff from './staff.flow.js';
import technicalLead from './technicalLead.flow.js';

export const screenFlows = Object.freeze({
  DEVELOPER: developer,
  STAFF: staff,
  MANAGER: manager,
  TECHNICAL_LEAD: technicalLead,
  ADMINISTRATOR: administrator,
});

export function getFlow(role) {
  const normalized = normalizeRole(role);
  return normalized ? screenFlows[normalized] : null;
}

/** Every screen of a flow, depth first, with its trail (module, parent screens, the screen itself). */
export function flattenFlow(flow) {
  if (!flow) return [];
  const result = [];
  const visit = (node, trail) => {
    const nextTrail = [...trail, node];
    if (node.type === 'screen') result.push({ node, trail: nextTrail });
    node.children.forEach((child) => visit(child, nextTrail));
  };
  flow.modules.forEach((moduleNode) => visit(moduleNode, []));
  return result;
}

// The flows are frozen constants, so the lookups used on every route change are built once.
const SCREENS_BY_PATH = Object.fromEntries(Object.entries(screenFlows).map(([role, flow]) => [
  role, new Map(flattenFlow(flow).map((entry) => [entry.node.path, entry])),
]));

const INTERNAL_PATHS = new Set(Object.values(SCREENS_BY_PATH).flatMap((byPath) => [...byPath.keys()]));

export function findScreen(role, path) {
  const normalized = normalizeRole(role);
  return (normalized && SCREENS_BY_PATH[normalized].get(path)) || null;
}

export function landingPath(role) {
  return getFlow(role)?.landing || null;
}

/** Paths that belong to the signed-in app in any role (used to tell 403 from an unknown URL). */
export function isInternalPath(path) {
  return INTERNAL_PATHS.has(path);
}

export function allInternalPaths() {
  return INTERNAL_PATHS;
}
