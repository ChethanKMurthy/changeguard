import Link from "next/link";

import { LogoMark } from "./logo";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto grid max-w-[1240px] gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="max-w-sm">
          <div className="flex items-center gap-2.5">
            <LogoMark className="size-6" />
            <span className="font-[640] tracking-[-0.02em] [font-stretch:115%]">ChangeGuard</span>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            An open-source research prototype for evidence-grounded code-change risk analysis. It never executes your
            code, and it never presents a heuristic as a fact.
          </p>
        </div>
        <FooterColumn
          title="Product"
          links={[
            ["/experience", "Guided experience"],
            ["/analyze", "Analyse a diff"],
            ["/history", "Reports"],
          ]}
        />
        <FooterColumn
          title="Research"
          links={[
            ["/evaluation", "Evaluation"],
            ["/method", "System card"],
            ["/method#rules", "Rule catalog"],
          ]}
        />
        <FooterColumn
          title="Engine"
          links={[
            ["/api/docs", "API reference"],
            ["/method#limitations", "Known limitations"],
            ["/method#security", "Threat model"],
          ]}
        />
      </div>
      <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-5 text-xs text-faint sm:px-6">
        <span>Sample scenarios are synthetic and labelled as such. Evaluation numbers come from the bundled dataset.</span>
        <span className="font-mono">MIT licensed</span>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      <ul className="mt-3 space-y-2">
        {links.map(([href, label]) => (
          <li key={href}>
            <Link href={href} className="text-sm text-muted transition-colors hover:text-ink">
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
