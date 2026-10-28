import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Company } from "./types";

export function Header({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) { return <header className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1></div>{action}</header>; }
export function State({ loading, error, empty, children }: { loading?: boolean; error?: string; empty?: string; children?: ReactNode }) { if (loading) return <div className="skeleton-grid"><div className="skeleton"/><div className="skeleton"/><div className="skeleton"/></div>; if (error) return <div className="alert error">{error}</div>; if (empty) return <div className="empty"><div className="empty-icon">◌</div><h3>{empty}</h3><p>Connect your backend and start with a real research run.</p></div>; return <>{children}</>; }
export function Score({ value }: { value: number | null }) { return <span title="Company opportunity score; persisted after scoring" className={`score score-${value === null ? "none" : value >= 75 ? "high" : value >= 45 ? "mid" : "low"}`}>{value === null ? "—" : value}</span>; }
export function CompanyCard({ company }: { company: Company }) {
  const location = company.location || company.country;
  return (
    <Link className="company-card" to={`/companies/${company.id}`}>
      <div className="company-logo">{company.name.slice(0, 1).toUpperCase()}</div>
      <div className="company-card-main">
        <div className="card-title-row">
          <h3>{company.name}</h3>
          <Score value={company.opportunity_score} />
        </div>
        <p>{company.description || "No verified company description yet."}</p>
        <div className="tag-row">
          {company.industry && <span className="tag">{company.industry}</span>}
          {company.company_stage && <span className="tag">{company.company_stage}</span>}
          {location && <span className="tag">{location}</span>}
          {company.hiring_status && company.hiring_status !== "not_specified" && (
            <span className="tag hiring-tag">Hiring: {company.hiring_status.replace("_", " ")}</span>
          )}
          {company.website_url && (
            <a
              className="tag link-tag"
              href={company.website_url}
              target="_blank"
              rel="noreferrer"
              onClick={e => e.stopPropagation()}
            >
              Website ↗
            </a>
          )}
        </div>
      </div>
    </Link>
  );
}
export function Button({ children, busy, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) { return <button className="button" disabled={busy || props.disabled} {...props}>{busy ? "Working…" : children}</button>; }
export function LinkButton({ children, to }: { children: ReactNode; to: string }) { return <Link className="button secondary" to={to}>{children}</Link>; }
