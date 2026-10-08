import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { CodeBlock } from "@/components/code/code";
import { ExperienceShell } from "@/components/experience/experience-shell";
import { Plate } from "@/components/experience/plate";
import { Figure } from "@/components/ui/primitives";
import { CIChart, type CIRow } from "@/components/viz/ci-chart";
import { cn } from "@/lib/cn";
import { isAISystem, isBaseline, shortSystemLabel, SPLIT_LABEL, systemLabel } from "@/lib/eval-format";
import { CATEGORY_LABEL, formatPercent } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";
import { evaluation, type EvalSystem } from "@/lib/static-data";

export const metadata: Metadata = {
  title: "Evaluation",
  description:
    "Precision, recall, negative controls, and evidence integrity on 67 labelled code changes, with bootstrap intervals, clean holdout results, baselines, an ablation, and three local language models.",
};

const SECTIONS = [
  { id: "holdout", n: "1", title: "Clean holdout results" },
  { id: "all-cases", n: "2", title: "All cases, current ruleset" },
  { id: "misses", n: "3", title: "What it misses" },
  { id: "ai", n: "4", title: "Language models" },
  { id: "provenance", n: "5", title: "Provenance and severity" },
  { id: "controls", n: "6", title: "Safe changes and evidence" },
  { id: "method", n: "7", title: "Method" },
  { id: "limitations", n: "8", title: "Limitations" },
];

function Section({ id, n, title, children }: { id: string; n: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-32 border-t border-line py-16 sm:py-20 lg:scroll-mt-24">
      <p className="font-mono text-[0.6875rem] text-muted">
        <span className="mr-2 inline-flex h-5 min-w-6 items-center justify-center rounded-[5px] bg-ink px-1.5 font-semibold text-bg">{n}</span>
        {title}
      </p>
      {children}
    </section>
  );
}

function H2({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={`${id}-title`} className="mt-4 max-w-[26ch] text-[clamp(1.65rem,2.9vw,2.35rem)] font-[640] leading-[1.12] tracking-[-0.027em] [font-stretch:112%]">
      {children}
    </h2>
  );
}

function Prose({ children }: { children: ReactNode }) {
  return <div className="prose-lab mt-6 space-y-4">{children}</div>;
}

function pct(value: number | null | undefined, digits = 1) {
  return formatPercent(value ?? null, digits);
}

function ci(range: [number | null, number | null] | undefined) {
  if (!range || range[0] == null || range[1] == null) return "";
  return `${Math.round(range[0] * 100)}–${Math.round(range[1] * 100)}`;
}

function tone(name: string): CIRow["tone"] {
  if (name === "changeguard") return "ink";
  if (isAISystem(name)) return "ai";
  if (name.startsWith("changeguard")) return "signal";
  return "muted";
}

function rowsFor(systems: EvalSystem[], metric: "precision" | "recall" | "f1"): CIRow[] {
  return systems.map((s) => ({
    key: s.system,
    label: systemLabel(s.system),
    value: s.overall[metric],
    low: s.ci95[metric][0],
    high: s.ci95[metric][1],
    emphasis: s.system === "changeguard",
    tone: tone(s.system),
  }));
}

export default function EvaluationPage() {
  const e = evaluation;
  const m = e.manifest;
  const systems = e.systems;
  const primary = systems.find((s) => s.system === "changeguard");
  const ruleSystems = systems.filter((s) => !isAISystem(s.system));
  const aiSystems = systems.filter((s) => isAISystem(s.system));
  const diffOnly = systems.find((s) => s.system === "changeguard-diff-only");
  const history = e.holdout_history?.runs ?? [];
  const historySystems = ["changeguard", "changeguard-diff-only", "baseline-keyword", "baseline-changed-symbols"];
  const aiInfo = m.ai as { mode?: string; provider?: string; prompt_version?: string; prompt_sha256?: string; decoding?: Record<string, number> };
  const generated = m.generated_at.slice(0, 10);
  const semanticFinds = e.misses.filter((x) => x.found_by.some(isAISystem));
  const aiNum = (s: EvalSystem, key: string) => {
    const v = s.ai[key];
    return typeof v === "number" ? v : 0;
  };

  return (
    <>
      <header className="mx-auto max-w-[1240px] px-4 pb-12 pt-14 sm:px-6 lg:pt-20">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-muted">
          <span>Evaluation</span>
          <span className="text-faint" aria-hidden="true">·</span>
          <span>ruleset {m.ruleset_version}</span>
          <span className="text-faint" aria-hidden="true">·</span>
          <span title={`sha256 ${m.dataset_sha256}`}>dataset {m.dataset_sha256.slice(0, 12)}…</span>
          <span className="text-faint" aria-hidden="true">·</span>
          <span>generated {generated}</span>
        </p>
        <h1 className="display mt-5 max-w-[19ch] text-[clamp(2.3rem,4.6vw,3.9rem)]">What the evaluation shows, and what it cannot.</h1>
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)] lg:gap-16">
          <p className="prose-lab text-[1.125rem]">
            {m.cases} labelled code changes, two naive baselines, an ablation without the repository snapshot, and three local
            language models, all scored with one-to-one matching and bootstrap intervals over cases. The dataset is small and
            synthetic, and the same author wrote it and the rules. Read every number with that in mind.
          </p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 self-start text-[0.8125rem]">
            {[
              ["Cases", `${m.cases}`, Object.entries(m.splits).map(([k, v]) => `${v} ${SPLIT_LABEL[k]?.toLowerCase() ?? k}`).join(" · ")],
              ["Labels", `${m.labels}`, "where a reviewer should look"],
              ["Negative controls", `${m.negative_controls}`, "safe changes; any finding is a false alarm"],
              ["Bootstrap", `${m.bootstrap.samples.toLocaleString("en-US")}`, `resamples over ${m.bootstrap.unit}s, seed ${m.bootstrap.seed}`],
            ].map(([label, value, hint]) => (
              <div key={label} className="border-t border-line pt-3">
                <dt className="text-[0.6875rem] text-muted">{label}</dt>
                <dd className="mt-0.5 text-2xl font-[650] tracking-[-0.03em] numeric [font-stretch:112%]">{value}</dd>
                <dd className="text-[0.6875rem] leading-snug text-muted">{hint}</dd>
              </div>
            ))}
          </dl>
        </div>
      </header>

      <ExperienceShell chapters={SECTIONS.map((s) => ({ id: s.id, n: s.n, title: s.title }))} heading="Contents">
        {/* ----------------------------------------------------------- 1 Holdout */}
        <Section id="holdout" n="1" title="Clean holdout results">
          <H2 id="holdout">Start with the numbers nothing was tuned on.</H2>
          <Prose>
            <p>
              The rules were written against the dev split. Two holdout sets were written afterwards, with the ruleset frozen,
              and each was run exactly once before anything changed. Those first runs are the closest thing here to an
              unbiased estimate. Every fix they prompted is listed, and later numbers on the same split no longer count as
              clean.
            </p>
          </Prose>
          <div className="mt-8 grid gap-6 xl:grid-cols-2">
            {history.map((run, k) => (
              <Figure
                key={run.split}
                number={`${k + 1}`}
                caption={
                  <>
                    {SPLIT_LABEL[run.split]}, first run: {run.cases} cases, {run.labels} labels, {run.negative_controls} negative
                    controls, ruleset {run.ruleset}. Point estimates only; raw console output is kept in{" "}
                    <code className="font-mono text-[0.75rem]">{run.raw_output}</code>.
                  </>
                }
              >
                <Plate label={`${run.split} · first run · ruleset ${run.ruleset}`} meta={run.date} bodyClassName="p-5">
                  <div className="grid gap-8 sm:grid-cols-2">
                    {(["precision", "recall"] as const).map((metric) => (
                      <CIChart
                        key={metric}
                        interval={null}
                        title={metric === "precision" ? "Precision" : "Recall"}
                        rows={historySystems
                          .filter((name) => run.systems[name])
                          .map((name) => ({
                            key: name,
                            label: systemLabel(name),
                            value: run.systems[name][metric],
                            emphasis: name === "changeguard",
                            tone: tone(name),
                          }))}
                      />
                    ))}
                  </div>
                  <p className="mt-5 border-t border-line pt-3 text-[0.75rem] text-muted">
                    False alarms on safe changes (ChangeGuard):{" "}
                    <span className="font-mono text-ink numeric">{pct(run.systems.changeguard?.negative_fp_rate, 0)}</span> of{" "}
                    {run.negative_controls} negative controls.
                  </p>
                </Plate>
              </Figure>
            ))}
          </div>
          {history.length > 0 && (
            <div className="mt-8 grid gap-6 lg:grid-cols-2">
              {history.map((run) => (
                <div key={run.split} className="rounded-[10px] border border-line bg-surface p-4">
                  <p className="text-[0.8125rem] font-semibold text-ink">Changed after the {SPLIT_LABEL[run.split]?.toLowerCase()} first run</p>
                  <ul className="mt-2 space-y-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">
                    {run.changes_after.map((change) => (
                      <li key={change} className="flex gap-2">
                        <span className="mt-[0.6em] size-1 shrink-0 rounded-full bg-signal" aria-hidden="true" />
                        <span>{renderInlineCode(change)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* -------------------------------------------------------- 2 All cases */}
        <Section id="all-cases" n="2" title="All cases, current ruleset">
          <H2 id="all-cases">All {m.cases} cases with the current rules, intervals included.</H2>
          <Prose>
            <p>
              These numbers include the dev split the rules were written against and the holdout cases after their fixes, so
              they are optimistic by construction. The intervals are 95% percentile bootstrap intervals over cases; with this
              few cases they are wide, and a perfect point estimate still comes with a lower bound.
            </p>
            {diffOnly && primary && (
              <p>
                The ablation is the most informative row. Without the repository snapshot, the same rules keep their precision
                but recall falls from {pct(primary.overall.recall)} to {pct(diffOnly.overall.recall)}: the missing share is
                what cross-file analysis (callers, imports, tests) contributes.
              </p>
            )}
          </Prose>
          <Figure
            number="3"
            className="mt-8"
            caption="Overall precision and recall per system, with 95% bootstrap intervals over cases."
          >
            <Plate label="all splits · current ruleset" meta={`${m.cases} cases · ${m.labels} labels`} bodyClassName="grid gap-10 p-5 sm:grid-cols-2">
              <CIChart title="Precision" rows={rowsFor(ruleSystems, "precision")} />
              <CIChart title="Recall" rows={rowsFor(ruleSystems, "recall")} />
            </Plate>
          </Figure>
          {primary && (
            <Figure number="4" className="mt-8" caption="ChangeGuard (no AI) by split. The dev split is where the rules were developed.">
              <Plate label="changeguard · by split" bodyClassName="grid gap-10 p-5 sm:grid-cols-2">
                {(["precision", "recall"] as const).map((metric) => (
                  <CIChart
                    key={metric}
                    title={metric === "precision" ? "Precision" : "Recall"}
                    rows={Object.entries(primary.by_split).map(([split, counts]) => ({
                      key: split,
                      label: `${SPLIT_LABEL[split] ?? split}`,
                      sublabel: `${counts.tp} TP · ${counts.fp} FP · ${counts.fn} FN`,
                      value: counts[metric],
                      low: primary.ci95_by_split?.[split]?.[metric]?.[0],
                      high: primary.ci95_by_split?.[split]?.[metric]?.[1],
                      emphasis: split !== "dev",
                      tone: split === "dev" ? "muted" : "ink",
                    }))}
                  />
                ))}
              </Plate>
            </Figure>
          )}
          <div className="mt-8 relative overflow-x-auto rounded-[12px] border border-line scrollbar-thin">
            <table className="w-full min-w-[720px] text-left text-[0.8125rem]">
              <caption className="sr-only">All systems: precision, recall and F1 with 95% intervals, negative-control false-positive rate.</caption>
              <thead className="bg-surface text-[0.6875rem] text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">System</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Precision [95% CI]</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Recall [95% CI]</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">F1</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">False alarms on safe changes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {systems.map((s) => (
                  <tr key={s.system} className={cn(s.system === "changeguard" && "bg-signal-tint/40")}>
                    <th scope="row" className="px-4 py-2.5 font-normal">
                      <span className={cn("block", s.system === "changeguard" ? "font-semibold text-ink" : "text-ink-soft")}>{systemLabel(s.system)}</span>
                      <span className="block text-[0.6875rem] text-muted">{s.description}</span>
                    </th>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {pct(s.overall.precision)} <span className="text-faint">[{ci(s.ci95.precision)}]</span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {pct(s.overall.recall)} <span className="text-faint">[{ci(s.ci95.recall)}]</span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">{pct(s.overall.f1)}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {pct(s.negative_controls.false_positive_rate, 0)}{" "}
                      <span className="text-faint">
                        ({s.negative_controls.cases_with_false_positive}/{s.negative_controls.cases})
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* ----------------------------------------------------------- 3 Misses */}
        <Section id="misses" n="3" title="What it misses">
          <H2 id="misses">
            {e.misses.length} labels missed, and why no rule caught them.
          </H2>
          <Prose>
            <p>
              Each miss below is a change whose problem lies in its meaning rather than its shape. Nothing syntactic
              distinguishes these lines from a correct edit, so a rule that flagged them would also flag a great many correct
              edits.
            </p>
            {semanticFinds.length > 0 && (
              <p>
                This is where a language model could earn its place, and it partly does:{" "}
                {Array.from(new Set(semanticFinds.flatMap((x) => x.found_by.filter(isAISystem).map((n) => n.replace("changeguard+ai:", "").replace(/@\d+$/, ""))))).map(
                  (model, i) => (
                    <span key={model}>
                      {i > 0 && " and "}
                      <code className="whitespace-nowrap">{model}</code>
                    </span>
                  ),
                )}{" "}
                found {semanticFinds.length} of these {e.misses.length}. The section on language models shows what that cost.
              </p>
            )}
          </Prose>
          <ul className="mt-8 grid gap-4 md:grid-cols-2">
            {e.misses.map((miss) => (
              <li key={`${miss.case}-${miss.label}`} className="rounded-[12px] border border-line bg-raised p-4">
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[0.625rem] text-faint">
                  <span>{miss.case}</span>
                  <span aria-hidden="true">·</span>
                  <span>{SPLIT_LABEL[miss.split] ?? miss.split}</span>
                  <span aria-hidden="true">·</span>
                  <span>{miss.label}</span>
                </p>
                <p className="mt-1.5 text-[0.9375rem] font-semibold text-ink">{miss.title}</p>
                <p className="mt-1 text-[0.8125rem] leading-relaxed text-ink-soft">{miss.description}</p>
                <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.75rem] text-muted">
                  <span className="rounded-[4px] border border-line px-1.5">{CATEGORY_LABEL[miss.category as keyof typeof CATEGORY_LABEL] ?? miss.category}</span>
                  <span className="font-mono">
                    {miss.file}
                    {miss.lines ? `:${miss.lines[0]}` : ""}
                  </span>
                </p>
                <p className={cn("mt-3 border-t border-line pt-2.5 text-[0.75rem]", miss.found_by.length ? "text-ai" : "text-muted")}>
                  {miss.found_by.length
                    ? `Found by ${miss.found_by.map(shortSystemLabel).join("; ")}`
                    : "Not found by any evaluated system."}
                </p>
              </li>
            ))}
          </ul>
        </Section>

        {/* -------------------------------------------------------------- 4 AI */}
        <Section id="ai" n="4" title="Language models">
          <H2 id="ai">Models ground their claims. Most of their new risks are still wrong.</H2>
          <Prose>
            <p>
              Each model ran locally through {aiInfo.provider ?? "a local provider"} on all {m.cases} cases with the same
              prompt (v{aiInfo.prompt_version}), greedy decoding, and a fixed seed. Every response is recorded, so these
              numbers replay exactly in CI without a model. The vote row samples three answers at temperature{" "}
              {aiInfo.decoding?.self_consistency_temperature ?? 0.7} and keeps a proposed risk only if a majority of samples
              agree.
            </p>
            <p>
              Two results hold across models. First, grounding works: no system cited evidence that failed the independent
              re-check, and the verifier rejected the claims that named findings, paths, or symbols the evidence did not
              support. Second, grounded is not the same as right. The larger model proposed many additional risks that cite
              real evidence and still match no label. That is why model findings sit in their own lane, are capped at medium
              confidence, and can never fail a build.
            </p>
          </Prose>
          <Figure
            number="5"
            className="mt-8"
            caption="Rules alone against rules plus each model. Recall rises slightly with the larger model; precision falls with every additional model-proposed risk that matches no label."
          >
            <Plate label="ai synthesis · replayed" meta={`prompt v${aiInfo.prompt_version ?? "?"}`} bodyClassName="grid gap-10 p-5 sm:grid-cols-2">
              <CIChart title="Precision" rows={rowsFor([primary, ...aiSystems].filter((s): s is EvalSystem => Boolean(s)), "precision")} />
              <CIChart title="Recall" rows={rowsFor([primary, ...aiSystems].filter((s): s is EvalSystem => Boolean(s)), "recall")} />
            </Plate>
          </Figure>
          <div className="mt-8 relative overflow-x-auto rounded-[12px] border border-line scrollbar-thin">
            <table className="w-full min-w-[760px] text-left text-[0.8125rem]">
              <caption className="sr-only">Per-model AI statistics: claims, rejections, model-proposed findings, cost.</caption>
              <thead className="bg-surface text-[0.6875rem] text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">Model</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Claims (rejected)</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Notes attached</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Model-proposed risks (matched a label)</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">False alarms on safe changes</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">Mean latency · tokens in/out</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {aiSystems.map((s) => (
                  <tr key={s.system}>
                    <th scope="row" className="whitespace-nowrap px-4 py-2.5 font-mono text-[0.75rem] font-normal text-ink">
                      {s.system.replace("changeguard+ai:", "")}
                    </th>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {aiNum(s, "claims_total")} <span className="text-faint">({aiNum(s, "claims_rejected")})</span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">{aiNum(s, "notes_applied")}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {aiNum(s, "ai_findings")} <span className="text-faint">({aiNum(s, "ai_true_positives")})</span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {pct(s.negative_controls.false_positive_rate, 0)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-[0.75rem] numeric">
                      {(aiNum(s, "mean_model_latency_ms") / 1000).toFixed(1)} s · {Math.round(aiNum(s, "mean_input_tokens"))}/
                      {Math.round(aiNum(s, "mean_output_tokens"))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {aiSystems.map((s) => {
              const reasons = (s.ai.rejection_reasons ?? {}) as Record<string, number>;
              const total = Object.values(reasons).reduce((a, b) => a + b, 0);
              return (
                <div key={s.system} className="rounded-[10px] border border-line p-4">
                  <p className="font-mono text-[0.6875rem] text-ink">{s.system.replace("changeguard+ai:", "")}</p>
                  <p className="mt-0.5 text-[0.6875rem] text-muted">Why claims were rejected</p>
                  <ul className="mt-3 space-y-2">
                    {Object.entries(reasons)
                      .sort((a, b) => b[1] - a[1])
                      .map(([reason, count]) => (
                        <li key={reason} className="text-[0.75rem]">
                          <div className="flex items-baseline justify-between gap-2">
                            <code className="font-mono text-[0.6875rem] text-ink-soft">{reason}</code>
                            <span className="font-mono text-muted numeric">{count}</span>
                          </div>
                          <div className="mt-1 h-1 rounded-full bg-surface-2" aria-hidden="true">
                            <div className="h-1 rounded-full bg-ai/70" style={{ width: `${total ? (count / total) * 100 : 0}%` }} />
                          </div>
                        </li>
                      ))}
                    {total === 0 && <li className="text-[0.75rem] text-muted">None rejected.</li>}
                  </ul>
                </div>
              );
            })}
          </div>
          <Prose>
            <p>
              Self-consistency helps, at a price. Voting over three samples dropped{" "}
              {(() => {
                const one = aiSystems.find((s) => s.system.endsWith("qwen2.5-coder:7b"));
                const three = aiSystems.find((s) => s.system.endsWith("@3"));
                return one && three ? `${aiNum(one, "ai_findings") - aiNum(three, "ai_findings")} of ${aiNum(one, "ai_findings")}` : "some";
              })()}{" "}
              model-proposed risks while keeping every one that matched a label, at roughly three times the tokens. The
              smaller model is quieter: it rarely proposes risks and mostly attaches explanations to findings the rules
              already made.
            </p>
            <p className="text-[0.9375rem] text-muted">
              Not measured: whether the explanations are correct or useful. That needs human rating, and none has been done.
            </p>
          </Prose>
        </Section>

        {/* ------------------------------------------------------ 5 Provenance */}
        <Section id="provenance" n="5" title="Provenance and severity">
          <H2 id="provenance">Precision by how a finding was established.</H2>
          <Prose>
            <p>
              Deterministic and heuristic findings are counted separately, as are confidence levels. A finding is{" "}
              <strong>acceptable</strong> when the case lists it as a reasonable extra observation, or when it is a second
              finding on a label already matched; acceptable findings count as neither true nor false positives. Most heuristic
              findings land there: test gaps a reviewer would agree with, but that the labels do not require.
            </p>
          </Prose>
          {primary && (
            <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <div className="relative overflow-x-auto rounded-[12px] border border-line scrollbar-thin">
                <table className="w-full min-w-[440px] text-left text-[0.8125rem]">
                  <caption className="sr-only">ChangeGuard precision by provenance and by confidence.</caption>
                  <thead className="bg-surface text-[0.6875rem] text-muted">
                    <tr>
                      <th scope="col" className="px-4 py-2.5 font-medium">Group</th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium">True positives</th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium">False positives</th>
                      <th scope="col" className="px-3 py-2.5 text-right font-medium">Acceptable</th>
                      <th scope="col" className="px-4 py-2.5 text-right font-medium">Precision</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {[
                      ...Object.entries(primary.by_kind).map(([k, v]) => [`◆ ◇ provenance: ${k}`, v] as const),
                      ...Object.entries(primary.by_confidence).map(([k, v]) => [`confidence: ${k}`, v] as const),
                    ].map(([label, v]) => (
                      <tr key={label}>
                        <th scope="row" className="px-4 py-2 font-normal text-ink-soft">
                          {label.replace("◆ ◇ ", "")}
                        </th>
                        <td className="px-3 py-2 text-right font-mono text-[0.75rem] numeric">{v.tp ?? 0}</td>
                        <td className="px-3 py-2 text-right font-mono text-[0.75rem] numeric">{v.fp ?? 0}</td>
                        <td className="px-3 py-2 text-right font-mono text-[0.75rem] numeric">{v.acceptable ?? 0}</td>
                        <td className="px-4 py-2 text-right font-mono text-[0.75rem] numeric">{pct(v.precision)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="rounded-[12px] border border-line p-5">
                <p className="text-[0.8125rem] font-semibold text-ink">Severity agreement on matched findings</p>
                <dl className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <dt className="text-[0.6875rem] text-muted">Exact</dt>
                    <dd className="text-2xl font-[650] tracking-[-0.03em] numeric [font-stretch:112%]">{pct(primary.severity_agreement.exact)}</dd>
                  </div>
                  <div>
                    <dt className="text-[0.6875rem] text-muted">Within one level</dt>
                    <dd className="text-2xl font-[650] tracking-[-0.03em] numeric [font-stretch:112%]">
                      {pct(primary.severity_agreement.within_one_level)}
                    </dd>
                  </div>
                </dl>
                <p className="mt-4 text-[0.75rem] leading-relaxed text-muted">
                  Severity is a categorical judgement per rule, compared with the labeller&rsquo;s. It is not a calibrated
                  probability and is never presented as one.
                </p>
              </div>
            </div>
          )}
          {primary && (
            <div className="mt-6 relative overflow-x-auto rounded-[12px] border border-line scrollbar-thin">
              <table className="w-full min-w-[480px] text-left text-[0.8125rem]">
                <caption className="sr-only">ChangeGuard recall by label category.</caption>
                <thead className="bg-surface text-[0.6875rem] text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-medium">Category</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Labels</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Found</th>
                    <th scope="col" className="px-4 py-2.5 font-medium">Recall</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {Object.entries(primary.by_category)
                    .sort((a, b) => (a[1].recall ?? 0) - (b[1].recall ?? 0) || b[1].tp - a[1].tp)
                    .map(([category, v]) => (
                      <tr key={category}>
                        <th scope="row" className="px-4 py-2 font-normal text-ink-soft">
                          {CATEGORY_LABEL[category as keyof typeof CATEGORY_LABEL] ?? category}
                        </th>
                        <td className="px-3 py-2 text-right font-mono text-[0.75rem] numeric">{v.tp + v.fn}</td>
                        <td className="px-3 py-2 text-right font-mono text-[0.75rem] numeric">{v.tp}</td>
                        <td className="px-4 py-2">
                          <span className="flex items-center gap-3">
                            <span className="h-1.5 w-28 shrink-0 rounded-full bg-surface-2" aria-hidden="true">
                              <span className={cn("block h-1.5 rounded-full", (v.recall ?? 0) < 1 ? "bg-signal" : "bg-ink/70")} style={{ width: `${(v.recall ?? 0) * 100}%` }} />
                            </span>
                            <span className="font-mono text-[0.75rem] numeric">{pct(v.recall)}</span>
                          </span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* -------------------------------------------------------- 6 Controls */}
        <Section id="controls" n="6" title="Safe changes and evidence">
          <H2 id="controls">Silence on safe changes, and evidence that checks out.</H2>
          <Prose>
            <p>
              {m.negative_controls} cases are safe changes with no label at all, so any finding on them is a false alarm. A
              review tool that cries wolf gets ignored, which makes this the number reviewers feel most.
            </p>
            <p>
              Separately, an independent checker re-reads each case&rsquo;s own files and verifies every evidence item a
              finding cites: it must exist, point at lines that exist in the stated revision, and quote those lines verbatim.
              A finding with any evidence that fails counts as unsupported.
            </p>
          </Prose>
          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <Plate label="negative controls" meta={`${m.negative_controls} safe changes`} bodyClassName="p-5">
              <ul className="space-y-3">
                {systems.map((s) => (
                  <li key={s.system} className="text-[0.8125rem]">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className={cn(s.system === "changeguard" ? "font-semibold text-ink" : "text-ink-soft")}>{systemLabel(s.system)}</span>
                      <span className="font-mono text-[0.75rem] text-muted numeric">
                        {s.negative_controls.cases_with_false_positive}/{s.negative_controls.cases}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-surface-2" aria-hidden="true">
                      <div
                        className={cn("h-1.5 rounded-full", isAISystem(s.system) ? "bg-ai/70" : isBaseline(s.system) ? "bg-faint" : "bg-ink/70")}
                        style={{ width: `${(s.negative_controls.false_positive_rate ?? 0) * 100}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </Plate>
            <Plate label="evidence integrity · independent re-check" bodyClassName="divide-y divide-line">
              {systems
                .filter((s) => !isBaseline(s.system))
                .map((s) => (
                  <div key={s.system} className="flex items-baseline justify-between gap-3 px-5 py-2.5 text-[0.8125rem]">
                    <span className="text-ink-soft">{systemLabel(s.system)}</span>
                    <span className="font-mono text-[0.75rem] numeric">
                      <span className={s.evidence.unsupported_findings ? "text-danger" : "text-ok"}>{s.evidence.unsupported_findings}</span>
                      <span className="text-muted"> of {s.evidence.findings_checked} unsupported</span>
                    </span>
                  </div>
                ))}
            </Plate>
          </div>
        </Section>

        {/* ---------------------------------------------------------- 7 Method */}
        <Section id="method" n="7" title="Method">
          <H2 id="method">How the numbers are produced.</H2>
          <div className="mt-8 grid gap-x-10 gap-y-6 md:grid-cols-2">
            {[
              ["Dataset", `${m.cases} cases, each a patch with the repository before the change and, for some, a coverage report. Each case lists expected labels (category, file, lines, severity) and acceptable extra observations. Labelling rules are in eval/LABELING.md.`],
              ["Matching", `${m.matching.rule[0].toUpperCase()}${m.matching.rule.slice(1)}. Precision and recall are micro-averaged over all labels.`],
              ["Intervals", `95% percentile bootstrap over ${m.bootstrap.unit}s, ${m.bootstrap.samples.toLocaleString("en-US")} resamples, seed ${m.bootstrap.seed}, overall and per split.`],
              ["Baselines", "A keyword search over added lines, and a system that flags every changed function. The diff-only ablation runs the same rules without the repository snapshot."],
              ["Language models", `Local inference through ${aiInfo.provider ?? "a local provider"}, temperature ${aiInfo.decoding?.temperature ?? 0} and seed ${aiInfo.decoding?.seed ?? "fixed"}. Responses are recorded per request fingerprint and replayed exactly.`],
              ["Regression gate", "CI replays the evaluation against a committed baseline. It fails if precision, recall or F1 drops by more than 2 points, the false-alarm rate rises by more than 5, unsupported evidence increases, or a previously found label is missed."],
            ].map(([title, body]) => (
              <div key={title} className="border-t border-line pt-4">
                <p className="text-[0.875rem] font-semibold text-ink">{title}</p>
                <p className="mt-1 text-[0.875rem] leading-relaxed text-ink-soft">{body}</p>
              </div>
            ))}
          </div>
          <div className="mt-8 grid items-start gap-5 lg:grid-cols-2">
            <CodeBlock
              title="Reproduce (no model needed: responses are replayed)"
              lang="bash"
              code={[
                "cd backend",
                'MODELS="llama3.2:3b,qwen2.5-coder:7b,qwen2.5-coder:7b@3"',
                "uv run changeguard eval --ai replay \\",
                '  --ai-model "$MODELS" \\',
                "  --check-baseline ../eval/baselines/changeguard.json",
              ].join("\n")}
            />
            <Plate label="run manifest" bodyClassName="divide-y divide-line font-mono text-[0.6875rem]">
              {[
                ["engine", `${m.changeguard_version} · ruleset ${m.ruleset_version}`],
                ["dataset sha256", m.dataset_sha256],
                ["prompt sha256", aiInfo.prompt_sha256 ?? "—"],
                ...Object.entries(m.environment).map(([k, v]) => [k, v ?? "—"]),
                ["generated", m.generated_at],
              ].map(([k, v]) => (
                <div key={k} className="grid grid-cols-[112px_minmax(0,1fr)] gap-3 px-4 py-2">
                  <span className="text-muted">{k}</span>
                  <span className="break-all text-ink-soft">{v}</span>
                </div>
              ))}
            </Plate>
          </div>
        </Section>

        {/* ---------------------------------------------------- 8 Limitations */}
        <Section id="limitations" n="8" title="Limitations">
          <H2 id="limitations">What these numbers do not say.</H2>
          <ol className="mt-8 space-y-4">
            {e.limitations.map((text, i) => (
              <li key={text} className="grid max-w-[78ch] grid-cols-[28px_minmax(0,1fr)] gap-3 text-[0.9375rem] leading-relaxed text-ink-soft">
                <span className="font-mono text-[0.75rem] text-muted numeric">{String(i + 1).padStart(2, "0")}</span>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <details className="group mt-12 rounded-[12px] border border-line">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-[0.875rem] font-medium text-ink">
              Per-case results for ChangeGuard ({e.cases.length} cases)
              <span className="text-muted transition-transform duration-200 group-open:rotate-45" aria-hidden="true">
                +
              </span>
            </summary>
            <div className="relative overflow-x-auto border-t border-line scrollbar-thin">
              <table className="w-full min-w-[640px] text-left text-[0.75rem]">
                <thead className="bg-surface text-[0.6875rem] text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-medium">Case</th>
                    <th scope="col" className="px-3 py-2 font-medium">Split</th>
                    <th scope="col" className="px-3 py-2 font-medium">Found</th>
                    <th scope="col" className="px-3 py-2 font-medium">Missed</th>
                    <th scope="col" className="px-4 py-2 font-medium">False positives</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line font-mono">
                  {e.cases.map((c) => (
                    <tr key={c.case}>
                      <th scope="row" className="px-4 py-1.5 font-normal text-ink-soft">
                        {c.case}
                        {c.negative && <span className="ml-1.5 font-sans text-[0.625rem] text-muted">safe</span>}
                      </th>
                      <td className="px-3 py-1.5 text-muted">{c.split}</td>
                      <td className="px-3 py-1.5 text-ok">{c.matched.join(", ") || "—"}</td>
                      <td className={cn("px-3 py-1.5", c.missed.length ? "text-signal" : "text-faint")}>{c.missed.join(", ") || "—"}</td>
                      <td className={cn("px-4 py-1.5", c.false_positives.length ? "text-danger" : "text-faint")}>{c.false_positives.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p className="mt-10 text-[0.875rem] text-muted">
            Want to see what a single analysis looks like?{" "}
            <Link href="/experience" className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal">
              Walk through one change
            </Link>{" "}
            or read{" "}
            <Link href="/method" className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal">
              how each rule works
            </Link>
            .
          </p>
        </Section>
      </ExperienceShell>
    </>
  );
}
