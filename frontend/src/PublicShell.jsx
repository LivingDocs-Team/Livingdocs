import HeroArt from './HeroArt';
import Icon from './icons';
import { PUBLIC_ROUTES } from './rbac/guard.js';
import { hrefFor } from './rbac/hashRoute.js';

/** Screen 1 (before sign-in): header with Home / Login / Register, hero on the left, `children` card on the right. */
export default function PublicShell({ page, children }) {
  return (
    <div className="public-shell">
      <header className="public-top">
        <div className="brand">
          <span className="logo"><Icon name="layers" size={17} /></span>
          LivingDocs
        </div>
        <nav aria-label="Public">
          {Object.entries(PUBLIC_ROUTES).map(([path, key]) => (
            <a key={key} href={hrefFor(path)} aria-current={page === key ? 'page' : undefined}>
              {key[0].toUpperCase() + key.slice(1)}
            </a>
          ))}
        </nav>
        <span className="ws-tag"><i aria-hidden="true" />Developer workspace</span>
      </header>

      <div className="public-grid">
        <section className="hero">
          <span className="hero-badge"><Icon name="spark" size={13} />Built for developers. Powered by AI.</span>
          <h1>
            <span className="sr-only">LivingDocs: </span>
            Your Code.<br />Your Documentation.
            <span className="hero-accent">One Workspace.</span>
          </h1>
          <p className="hero-lead">Connect your repositories. Create living documentation. Let AI bring it all together.</p>
          <div className="hero-art"><HeroArt /></div>
        </section>
        <aside className="auth-card fx">{children}</aside>
      </div>

      <footer className="public-foot">
        <span>© 2026 LivingDocs</span>
        <span><Icon name="lock" size={13} />Your workspace. Secure by design.</span>
      </footer>
    </div>
  );
}
