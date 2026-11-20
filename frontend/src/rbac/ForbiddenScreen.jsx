import { hrefFor } from './hashRoute.js';
import PageFrame from './PageFrame';

/** Shown when a signed-in user opens an internal URL that their role may not access. */
export default function ForbiddenScreen({ landing }) {
  return (
    <PageFrame title="Access denied" titleId="rbac-forbidden-title" className="rbac-forbidden" eyebrow="403">
      <p role="alert">Your role does not have permission to open this page.</p>
      {landing && <a className="rbac-link-button" href={hrefFor(landing)}>Go to your home page</a>}
    </PageFrame>
  );
}
