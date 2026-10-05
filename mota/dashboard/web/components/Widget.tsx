"use client";
// Widget = titled panel that can span a 12-column grid; Stat = KPI tile.
import type { ReactNode } from "react";

export function Widget({ title, badge, actions, footer, span, className = "", bodyClass = "", flush, testId, children }: {
  title?: ReactNode; badge?: ReactNode; actions?: ReactNode; footer?: ReactNode;
  span?: number; className?: string; bodyClass?: string; flush?: boolean; testId?: string; children: ReactNode;
}) {
  return (
    <section className={`widget ${className}`} data-testid={testId}
             style={span ? { gridColumn: `span ${span} / span ${span}` } : undefined}>
      {(title || actions || badge) && (
        <header>
          {title && <span className="w-title">{title}</span>}
          {badge}
          {actions && <span className="w-actions">{actions}</span>}
        </header>
      )}
      <div className={`body ${flush ? "flush" : ""} ${bodyClass}`}>{children}</div>
      {footer && <footer>{footer}</footer>}
    </section>
  );
}

export function Stat({ label, value, sub, tone, title }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: "ok" | "warn" | "bad"; title?: string;
}) {
  return (
    <div className={`stat ${tone ?? ""}`} title={title} data-testid={`stat-${label.toLowerCase().replace(/\W+/g, "-")}`}>
      <span className="k">{label}</span>
      <span className="v">{value}</span>
      {sub != null && <span className="s truncate">{sub}</span>}
    </div>
  );
}
