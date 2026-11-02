import type { ReactNode } from "react";

/** A horizontal strip of key figures. Plain definition-list semantics, no decorative cards. */
export function StatStrip({ items }: { items: { label: string; value: string; hint?: string }[] }) {
  return (
    <dl className="stat-strip">
      {items.map((it) => (
        <div className="stat" key={it.label}>
          <dt>{it.label}</dt>
          <dd>{it.value}</dd>
          {it.hint && <p>{it.hint}</p>}
        </div>
      ))}
    </dl>
  );
}

export function Section({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      <h2>{title}</h2>
      {note && <p className="note">{note}</p>}
      {children}
    </section>
  );
}

export function Panel({ title, children, wide = false }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <figure className={`panel${wide ? " wide" : ""}`}>
      <figcaption>{title}</figcaption>
      {children}
    </figure>
  );
}

export function Status({ loading, error, children }: { loading: boolean; error: string | null; children: ReactNode }) {
  if (error) {
    return (
      <div className="status error" role="alert">
        <strong>Could not load data.</strong> {error}
      </div>
    );
  }
  return (
    <div className={loading ? "is-loading" : ""} aria-busy={loading}>
      {children}
    </div>
  );
}
