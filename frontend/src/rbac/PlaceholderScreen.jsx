import PageFrame from './PageFrame';
import { PERMISSIONS } from './permissions.js';

/** Shared page for screens that are in a role's flow but not built yet (status: 'placeholder'). */
export default function PlaceholderScreen({ node, trail = [] }) {
  const permission = PERMISSIONS[node.permissionKey];
  return (
    <PageFrame
      title={node.label}
      titleId="rbac-placeholder-title"
      className="rbac-placeholder"
      eyebrow="Chưa triển khai · Not implemented yet"
      subtitle="This screen is part of your role's screen flow but has not been built yet."
    >
      <dl className="rbac-placeholder-details">
        <dt>Location</dt>
        <dd>{trail.map((item) => item.label).join(' › ')}</dd>
        {permission && (
          <>
            <dt>Permission</dt>
            <dd>#{permission.row} {permission.label}</dd>
          </>
        )}
      </dl>
    </PageFrame>
  );
}
