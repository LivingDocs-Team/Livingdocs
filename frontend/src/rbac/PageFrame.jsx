/** The page frame shared by the shell's own pages (placeholder, 403, child index, framed panels). */
export default function PageFrame({ title, titleId, className = '', eyebrow, subtitle, actions, children }) {
  return (
    <main className="page">
      <section className={`login-card ${className}`.trim()} aria-labelledby={titleId}>
        {eyebrow && <p className="rbac-placeholder-tag">{eyebrow}</p>}
        <div className="page-head">
          <div>
            <h1 id={titleId}>{title}</h1>
            {subtitle && <p className="subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="page-actions">{actions}</div>}
        </div>
        {children}
      </section>
    </main>
  );
}
