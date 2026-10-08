"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import type { Evidence, Finding } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { CATEGORY_LABEL, formatLocation, languageForPath } from "@/lib/format";

import { CodeBlock } from "../code/code";
import { ConfidenceMeter, EvidenceTag, Pill, ProvenanceBadge, SeverityBadge } from "../ui/badges";
import { EvidenceCard, renderInlineCode } from "./evidence";

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-line pt-5">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <h3 className="text-[0.8125rem] font-semibold text-ink">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function FindingInspector({
  finding,
  evidence,
  onShowInDiff,
}: {
  finding: Finding;
  evidence: Map<string, Evidence>;
  onShowInDiff?: (finding: Finding) => void;
}) {
  const reduce = useReducedMotion();
  const [activeEvidence, setActiveEvidence] = useState<string | null>(null);
  const cited = finding.evidence_ids.map((id) => evidence.get(id)).filter((e): e is Evidence => Boolean(e));
  const ai = finding.ai_analysis;
  const test = finding.suggested_test;

  const focusEvidence = (id: string) => {
    setActiveEvidence(id);
    document.getElementById(`evidence-${id}`)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest" });
  };

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.article
        key={finding.id}
        initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        className="space-y-5"
        aria-labelledby={`finding-title-${finding.id}`}
      >
        <header className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <span className="text-line-strong" aria-hidden="true">/</span>
            <ProvenanceBadge kind={finding.kind} />
            <ConfidenceMeter confidence={finding.confidence} />
          </div>
          <h2 id={`finding-title-${finding.id}`} className="text-xl font-semibold leading-snug tracking-[-0.01em] text-ink">
            {renderInlineCode(finding.title)}
          </h2>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[0.8125rem]">
            <button
              type="button"
              onClick={() => onShowInDiff?.(finding)}
              className="inline-flex items-center gap-1.5 rounded font-mono text-[0.75rem] text-ink underline decoration-line-strong underline-offset-[3px] transition-colors hover:decoration-signal"
            >
              {formatLocation(finding.location.file, finding.location.start_line, finding.location.end_line)}
              {finding.location.side === "base" && <span className="text-muted">(removed code)</span>}
            </button>
            <span className="text-faint" aria-hidden="true">·</span>
            <Link href={`/method#rule-${finding.rule_id}`} className="font-mono text-[0.75rem] text-muted hover:text-ink">
              {finding.rule_id}
            </Link>
            <span className="text-faint" aria-hidden="true">·</span>
            <span className="text-muted">{CATEGORY_LABEL[finding.category]}</span>
          </div>
          <p className="text-[0.9375rem] leading-relaxed text-ink-soft">{renderInlineCode(finding.description)}</p>
          {finding.corroborated_by.length > 0 && (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
              Corroborated by
              {finding.corroborated_by.map((rule) => (
                <Pill key={rule} tone={rule === "ai" ? "ai" : "neutral"} className="h-5 font-mono text-[0.6875rem]">
                  {rule === "ai" ? "✦ AI" : rule}
                </Pill>
              ))}
            </p>
          )}
        </header>

        <Section title="Why it matters">
          <p className="text-[0.875rem] leading-relaxed text-ink-soft">{renderInlineCode(finding.explanation.text)}</p>
        </Section>

        <Section title="Failure scenario">
          <p className="text-[0.875rem] leading-relaxed text-ink-soft">{renderInlineCode(finding.failure_scenario)}</p>
        </Section>

        <Section
          title={`Evidence (${cited.length})`}
          aside={
            <span className="flex flex-wrap gap-1">
              {cited.map((e) => (
                <EvidenceTag key={e.id} id={e.id} active={activeEvidence === e.id} onClick={() => focusEvidence(e.id)} />
              ))}
            </span>
          }
        >
          <div className="space-y-3">
            {cited.map((e) => (
              <EvidenceCard key={e.id} evidence={e} active={activeEvidence === e.id} />
            ))}
          </div>
        </Section>

        <Section title={`Suggested ${test.kind === "review" ? "review step" : `${test.kind} check`}`}>
          <p className="text-[0.875rem] leading-relaxed text-ink-soft">{renderInlineCode(test.description)}</p>
          {test.code && (
            <CodeBlock
              className="mt-3"
              code={test.code}
              lang={test.language === "shell" ? "bash" : test.language ?? languageForPath(finding.location.file)}
              title={test.source === "ai" ? "AI-suggested — not executed" : "Generated from the analysis — not executed"}
            />
          )}
        </Section>

        {ai && finding.kind !== "ai" && (
          <section className="rounded-[10px] border border-ai/30 bg-ai-tint p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="text-ai" aria-hidden="true">✦</span>
              <h3 className="text-[0.8125rem] font-semibold text-ink">AI analysis</h3>
              <span className="font-mono text-[0.6875rem] text-muted">{ai.model}</span>
              <Pill tone="ok" className="ml-auto h-5 text-[0.6875rem]">Passed grounding checks</Pill>
            </div>
            <div className="space-y-2.5 text-[0.875rem] leading-relaxed text-ink-soft">
              <p>{renderInlineCode(ai.explanation)}</p>
              {ai.failure_scenario && (
                <p>
                  <span className="font-medium text-ink">Scenario. </span>
                  {renderInlineCode(ai.failure_scenario)}
                </p>
              )}
              {ai.uncertainty && (
                <p>
                  <span className="font-medium text-ink">Uncertainty. </span>
                  {renderInlineCode(ai.uncertainty)}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted">
                <ConfidenceMeter confidence={ai.confidence} />
                <span aria-hidden="true">·</span>
                cites
                {ai.evidence_ids.map((id) => (
                  <EvidenceTag key={id} id={id} onClick={() => focusEvidence(id)} />
                ))}
              </div>
            </div>
            <p className="mt-3 border-t border-ai/20 pt-2.5 text-[0.75rem] leading-relaxed text-muted">
              Model output is shown separately from the rule&rsquo;s analysis and never changes the finding&rsquo;s severity,
              confidence, or evidence.
            </p>
          </section>
        )}

        {finding.kind === "ai" && (
          <p className={cn("rounded-[10px] border border-ai/30 bg-ai-tint p-3.5 text-[0.8125rem] leading-relaxed text-ink-soft")}>
            <span className="font-semibold text-ai">✦ Proposed by a model.</span> This risk was not established by deterministic
            analysis. It was kept because every evidence item it cites exists and its file, line, and symbol references checked
            out. Confidence is capped at medium.
          </p>
        )}
      </motion.article>
    </AnimatePresence>
  );
}
