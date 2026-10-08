"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

import { cn } from "@/lib/cn";
import type { AIFigure } from "@/lib/experience-data";
import { formatDuration } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";

import { EvidenceTag } from "../ui/badges";
import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;

const CHECKS: { code: string; text: string }[] = [
  { code: "unknown_finding", text: "A note must attach to a finding in this report." },
  { code: "no_evidence", text: "Every claim cites at least one evidence ID." },
  { code: "unknown_evidence", text: "Every cited ID was produced for this change." },
  { code: "unknown_path", text: "Every file path named is part of the change or its evidence." },
  { code: "line_out_of_range", text: "Every line number falls inside the evidence it cites." },
  { code: "symbol_not_in_evidence", text: "Every function named appears in the cited evidence." },
  { code: "unsupported_number", text: "Every percentage appears in the evidence." },
  { code: "claims_test_result", text: "No claim says a test passed or failed. None were run." },
];

function Station({
  index,
  title,
  tone = "neutral",
  children,
  play,
}: {
  index: number;
  title: string;
  tone?: "neutral" | "ai" | "ok";
  children: React.ReactNode;
  play: boolean;
}) {
  return (
    <motion.li
      initial={play ? { opacity: 0, y: 8 } : false}
      animate={play ? { opacity: 1, y: 0 } : undefined}
      transition={{ duration: 0.4, delay: 0.15 + index * 0.32, ease: EASE }}
      className={cn(
        "relative z-10 rounded-[10px] border p-3",
        tone === "ai" ? "border-ai/40 bg-ai-tint" : tone === "ok" ? "border-ok/35 bg-ok-tint" : "border-line bg-bg",
      )}
    >
      <p className="font-mono text-[0.625rem] text-faint">0{index + 1}</p>
      <p className="mt-0.5 text-[0.8125rem] font-semibold text-ink">{title}</p>
      <div className="mt-1.5 space-y-0.5 text-[0.6875rem] leading-relaxed text-muted">{children}</div>
    </motion.li>
  );
}

/** Fig. 9: one recorded AI pass — what the model saw, what it was allowed to say, and what survived verification. */
export function FigAI({ data }: { data: AIFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.25 });
  const play = !reduce && inView;

  return (
    <Plate label="ai synthesis + grounding verification · recorded" meta={data.model ? `${data.provider} / ${data.model} · local` : undefined}>
      <div ref={ref} className="p-4 sm:p-5">
        <div className="relative">
          {/* Signal line behind the stations */}
          <span className="absolute left-[18px] top-4 bottom-4 w-px bg-line md:left-4 md:right-4 md:top-[38px] md:bottom-auto md:h-px md:w-auto" aria-hidden="true" />
          <motion.span
            className="absolute left-[17.5px] top-4 hidden h-2 w-2 -translate-y-1/2 rounded-full bg-ai-glow shadow-[0_0_0_4px_var(--ai-tint)] md:block md:top-[38px]"
            initial={play ? { left: "2%", opacity: 0 } : false}
            animate={play ? { left: ["2%", "98%"], opacity: [0, 1, 1, 0] } : undefined}
            transition={{ duration: 1.9, delay: 0.2, ease: "easeInOut" }}
            aria-hidden="true"
          />
          <ol className="grid gap-3 md:grid-cols-5">
            <Station index={0} title="Evidence pack" play={play}>
              <p>
                <span className="font-mono text-ink numeric">{data.contextChars.toLocaleString("en-US")}</span> chars
                {data.truncated && <span className="text-signal"> · trimmed to budget</span>}
              </p>
              <p>excerpts fenced as untrusted</p>
              <p>secrets masked · injection lines withheld</p>
            </Station>
            <Station index={1} title="Model" tone="ai" play={play}>
              <p className="font-mono text-ink">{data.model}</p>
              <p>{data.provider} · local inference</p>
              <p className="numeric">
                {data.inputTokens.toLocaleString("en-US")} → {data.outputTokens.toLocaleString("en-US")} tokens · {formatDuration(data.latencyMs)}
              </p>
            </Station>
            <Station index={2} title="Closed schema" play={play}>
              <p>every claim cites evidence IDs</p>
              <p>no file or line fields to fill</p>
              <p>AI risks: confidence ≤ medium</p>
            </Station>
            <Station index={3} title="Verifier" play={play}>
              <p>{CHECKS.length} checks per claim</p>
              <p>a failed check rejects the claim</p>
              <p>claims are never repaired</p>
            </Station>
            <Station index={4} title="Result" tone="ok" play={play}>
              <p>
                <span className="font-mono text-ink numeric">{data.claims}</span> claims ·{" "}
                <span className="font-mono text-ok numeric">{data.accepted}</span> accepted ·{" "}
                <span className="font-mono text-ink numeric">{data.rejected}</span> rejected
              </p>
              <p>shown beside the rule&rsquo;s analysis, never in place of it</p>
            </Station>
          </ol>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          {data.note && (
            <div className="rounded-[10px] border border-ai/35 bg-ai-tint p-4">
              <p className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted">
                <span className="font-semibold text-ai">✦ Shown</span>
                <span>verified note on {data.note.ruleId}</span>
              </p>
              <p className="mt-2 text-[0.8125rem] font-medium text-ink">{renderInlineCode(data.note.findingTitle)}</p>
              <blockquote className="mt-2 text-[0.8125rem] leading-relaxed text-ink-soft">&ldquo;{renderInlineCode(data.note.explanation)}&rdquo;</blockquote>
              <p className="mt-3 flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-muted">
                cites {data.note.evidenceIds.map((id) => <EvidenceTag key={id} id={id} />)}
                <span aria-hidden="true">·</span> model confidence {data.note.confidence}
              </p>
            </div>
          )}
          {data.assessment && (
            <div className="rounded-[10px] border border-dashed border-line-strong p-4">
              <p className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted">
                <span className="font-semibold text-ink-soft">Not shown</span>
                <span>free-text summary, kept in the JSON trace</span>
              </p>
              <blockquote className="mt-2 text-[0.8125rem] italic leading-relaxed text-muted">
                &ldquo;{data.assessment}&rdquo;
              </blockquote>
              {data.assessmentIssue && (
                <p className="mt-3 text-[0.75rem] leading-relaxed text-ink-soft">
                  It places the condition change in <code className="rounded bg-surface-2 px-1 font-mono text-[0.86em]">{data.assessmentIssue.claimed}</code>.
                  The report places it in <code className="rounded bg-surface-2 px-1 font-mono text-[0.86em]">{data.assessmentIssue.actual}</code>.
                  Prose like this cannot be checked claim by claim, so it is never displayed as analysis.
                </p>
              )}
            </div>
          )}
        </div>

        <div className="mt-6">
          <h3 className="text-[0.8125rem] font-semibold text-ink">Checks applied to every claim</h3>
          <ul className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {CHECKS.map((check, i) => (
              <motion.li
                key={check.code}
                className="grid grid-cols-[18px_minmax(0,1fr)] gap-2 text-[0.75rem]"
                initial={play ? { opacity: 0 } : false}
                animate={play ? { opacity: 1 } : undefined}
                transition={{ duration: 0.3, delay: 1.9 + i * 0.06 }}
              >
                <svg viewBox="0 0 16 16" className="mt-0.5 size-3.5 text-ok" aria-hidden="true">
                  <path d="M3.5 8.4 6.6 11.4 12.6 4.8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="min-w-0">
                  <code className="font-mono text-[0.6875rem] text-ink">{check.code}</code>
                  <span className="block text-muted">{check.text}</span>
                </span>
              </motion.li>
            ))}
          </ul>
        </div>
      </div>
      {data.promptSha && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-line bg-surface px-4 py-2.5 font-mono text-[0.625rem] text-faint">
          <span>
            prompt {data.promptId} v{data.promptVersion}
          </span>
          <span title={`sha256 ${data.promptSha}`}>prompt sha256 {data.promptSha.slice(0, 12)}…</span>
          {data.requestSha && <span title={`sha256 ${data.requestSha}`}>request sha256 {data.requestSha.slice(0, 12)}…</span>}
          <span>recorded when the site was built</span>
        </div>
      )}
    </Plate>
  );
}
