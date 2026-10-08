import type { Metadata } from "next";
import Link from "next/link";

import { CodeBlock } from "@/components/code/code";
import { HeroInstrument } from "@/components/landing/hero-instrument";
import { EvidenceTag } from "@/components/ui/badges";
import { ButtonLink } from "@/components/ui/button";
import { Figure } from "@/components/ui/primitives";
import { CIChart, type CIRow } from "@/components/viz/ci-chart";
import type { Finding } from "@/lib/api/types";
import { formatDuration, formatPercent } from "@/lib/format";
import { systemLabel } from "@/lib/eval-format";
import { renderInlineCode } from "@/lib/inline-code";
import { STAGES } from "@/lib/stages";
import { evaluation, instrumentData, sampleReport, sampleReportAI } from "@/lib/static-data";

export const metadata: Metadata = {
  title: { absolute: "ChangeGuard — evidence for every risk in your diff" },
};


function findingByRule(rule: string): Finding | undefined {
  return sampleReport.findings.find((f) => f.rule_id === rule);
}

export default function Home() {
  const instrument = instrumentData();
  const breaking = findingByRule("CG-API-001");
  const logic = findingByRule("CG-LOG-001");
  const aiNote = sampleReportAI.findings.find((f) => f.ai_analysis && f.kind !== "ai");
  const callEvidence = breaking
    ? sampleReport.evidence.find((e) => breaking.evidence_ids.includes(e.id) && e.type === "call_site")
    : undefined;
  const problems = Array.isArray(callEvidence?.data.problems) ? (callEvidence.data.problems as string[]) : [];

  const primary = evaluation.systems.find((s) => s.system === "changeguard");
  const deterministicSystems = evaluation.systems.filter((s) => !s.system.startsWith("changeguard+ai"));
  const rows = (metric: "precision" | "recall"): CIRow[] =>
    deterministicSystems.map((s) => ({
      key: s.system,
      label: systemLabel(s.system),
      value: s.overall[metric],
      low: s.ci95[metric][0],
      high: s.ci95[metric][1],
      emphasis: s.system === "changeguard",
      tone: s.system === "changeguard" ? "ink" : s.system.startsWith("changeguard") ? "signal" : "muted",
    }));
  const cleanRuns = (evaluation.holdout_history?.runs ?? []).flatMap((run) =>
    run.systems.changeguard ? [{ split: run.split, cases: run.cases, ruleset: run.ruleset, ...run.systems.changeguard }] : [],
  );
  const pipelineMs = sampleReport.pipeline.reduce((sum, s) => sum + s.duration_ms, 0);
  const stageMs = new Map(sampleReport.pipeline.map((s) => [s.name, s]));

  return (
    <>
      {/* ---------------------------------------------------------------- Hero */}
      <section className="relative">
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 items-center gap-14 px-4 pb-20 pt-12 sm:px-6 lg:grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)] lg:gap-16 lg:pb-28 lg:pt-20">
          <div className="min-w-0">
            <p className="flex items-center gap-2.5 text-sm text-muted">
              <span className="font-mono text-ink" aria-hidden="true">
                ◆ ◇ <span className="text-ai">✦</span>
              </span>
              Code-change risk analysis, with provenance
            </p>
            <h1 className="display mt-6 text-[clamp(2.5rem,4.6vw,4.1rem)]">Evidence for every risk in your diff.</h1>
            <p className="prose-lab mt-7 text-[1.125rem] leading-[1.65]">
              ChangeGuard reads a change the way a careful reviewer does. It rebuilds both revisions, follows every caller,
              reruns static analysis on what is new, and measures the lines your tests never touch. A language model may
              explain the result, but only where the evidence holds.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <ButtonLink href="/experience" size="lg">
                Take the guided experience
                <span aria-hidden="true">→</span>
              </ButtonLink>
              <ButtonLink href="/analyze" size="lg" variant="secondary">
                Analyse a diff
              </ButtonLink>
            </div>
            <p className="mt-10 max-w-lg border-t border-line pt-5 text-[0.8125rem] leading-relaxed text-muted">
              Python, JavaScript and TypeScript in depth; secrets, migrations, and dependencies for any file. Runs locally,
              needs no API key, and never executes the code it reads.
            </p>
          </div>
          <Figure
            number="1"
            caption={
              <>
                A replay of a real run on the billing sample (synthetic data): a refactor that drops a parameter callers still
                pass. {instrument.totalFindings} findings in {formatDuration(instrument.totalMs)}.{" "}
                <Link href="/experience" className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal">
                  Walk through it
                </Link>
                .
              </>
            }
          >
            <HeroInstrument data={instrument} />
          </Figure>
        </div>
      </section>

      {/* ---------------------------------------------------- Provenance ladder */}
      <section className="border-t border-line">
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 gap-12 px-4 py-24 sm:px-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)] lg:gap-20 lg:py-32">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <h2 className="text-[clamp(1.9rem,3.4vw,2.8rem)] font-[640] leading-[1.08] tracking-[-0.03em] [font-stretch:112%]">
              A finding is only as good as the way it was found.
            </h2>
            <p className="prose-lab mt-5">
              Most review tools merge everything into one confident list. ChangeGuard keeps three kinds of knowledge apart,
              labels each finding with its kind, and never lets a weaker kind overrule a stronger one.
            </p>
          </div>
          <ol className="border-y border-line">
            <li className="grid grid-cols-1 gap-5 border-b border-line py-8 sm:grid-cols-[72px_minmax(0,1fr)]">
              <span className="flex size-14 items-center justify-center rounded-[12px] bg-ink text-2xl text-bg" aria-hidden="true">
                ◆
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-3">
                  <h3 className="text-xl font-semibold tracking-[-0.01em]">Deterministic</h3>
                  <span className="text-sm text-muted">established by analysis</span>
                </div>
                <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-soft">
                  A parse, a resolved call, a measured line. If the rule says a caller passes a keyword the new signature
                  rejects, it found that call and checked it the way Python binds arguments.
                </p>
                {breaking && (
                  <div className="mt-4 rounded-[10px] border border-line bg-surface p-3.5">
                    <p className="text-[0.8125rem] font-medium">{renderInlineCode(breaking.title)}</p>
                    {problems[0] && <p className="mt-1.5 text-xs text-danger">× {renderInlineCode(problems[0])}</p>}
                    <p className="mt-2 flex flex-wrap items-center gap-1.5 font-mono text-[0.6875rem] text-muted">
                      {breaking.location.file}:{breaking.location.start_line}
                      {breaking.evidence_ids.map((id) => (
                        <EvidenceTag key={id} id={id} />
                      ))}
                    </p>
                  </div>
                )}
              </div>
            </li>
            <li className="grid grid-cols-1 gap-5 border-b border-line py-8 sm:grid-cols-[72px_minmax(0,1fr)]">
              <span className="flex size-14 items-center justify-center rounded-[12px] border-2 border-ink text-2xl text-ink" aria-hidden="true">
                ◇
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-3">
                  <h3 className="text-xl font-semibold tracking-[-0.01em]">Heuristic</h3>
                  <span className="text-sm text-muted">inferred by a rule</span>
                </div>
                <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-soft">
                  A pattern worth a reviewer&rsquo;s attention whose impact depends on context: a flipped comparison, a
                  function no test references. Stated as an inference, with its confidence, never as a fact.
                </p>
                {logic && (
                  <div className="mt-4 rounded-[10px] border border-line bg-surface p-3.5">
                    <p className="text-[0.8125rem] font-medium">{renderInlineCode(logic.title)}</p>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted">{renderInlineCode(logic.failure_scenario)}</p>
                    <p className="mt-2 flex flex-wrap items-center gap-1.5 font-mono text-[0.6875rem] text-muted">
                      {logic.location.file}:{logic.location.start_line}
                      {logic.evidence_ids.map((id) => (
                        <EvidenceTag key={id} id={id} />
                      ))}
                    </p>
                  </div>
                )}
              </div>
            </li>
            <li className="grid grid-cols-1 gap-5 py-8 sm:grid-cols-[72px_minmax(0,1fr)]">
              <span className="flex size-14 items-center justify-center rounded-[12px] border border-ai/40 bg-ai-tint text-2xl text-ai" aria-hidden="true">
                ✦
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-3">
                  <h3 className="text-xl font-semibold tracking-[-0.01em]">AI-generated</h3>
                  <span className="text-sm text-muted">proposed by a model, then verified</span>
                </div>
                <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-soft">
                  Explanations and extra risks from a language model, kept only if every evidence ID, file, line, and symbol
                  they mention checks out. Shown beside the rule&rsquo;s analysis, never in place of it.
                </p>
                {aiNote?.ai_analysis && (
                  <div className="mt-4 rounded-[10px] border border-ai/30 bg-ai-tint p-3.5">
                    <p className="text-[0.8125rem] leading-relaxed text-ink-soft">&ldquo;{renderInlineCode(aiNote.ai_analysis.explanation)}&rdquo;</p>
                    <p className="mt-2 flex flex-wrap items-center gap-1.5 font-mono text-[0.6875rem] text-muted">
                      {aiNote.ai_analysis.model} · local, via Ollama · cites
                      {aiNote.ai_analysis.evidence_ids.map((id) => (
                        <EvidenceTag key={id} id={id} />
                      ))}
                    </p>
                  </div>
                )}
              </div>
            </li>
          </ol>
        </div>
      </section>

      {/* ------------------------------------------------------------ Pipeline */}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto max-w-[1240px] px-4 py-24 sm:px-6 lg:py-32">
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)] lg:gap-20">
            <div>
              <h2 className="text-[clamp(1.9rem,3.4vw,2.8rem)] font-[640] leading-[1.08] tracking-[-0.03em] [font-stretch:112%]">
                Eleven stages, all of them visible.
              </h2>
              <p className="prose-lab mt-5">
                No single score hides the work. Every report records what each stage did, how long it took, and what it
                skipped and why. On the billing sample the full deterministic pipeline took{" "}
                <strong className="numeric">{formatDuration(pipelineMs)}</strong>.
              </p>
              <ButtonLink href="/method" variant="secondary" className="mt-8">
                Read the system card
              </ButtonLink>
            </div>
            <ol className="grid gap-x-10 gap-y-0 sm:grid-cols-2">
              {STAGES.map((stage, i) => {
                const result = stageMs.get(stage.name);
                return (
                  <li key={stage.name} className="border-t border-line py-4">
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="flex items-baseline gap-2.5 text-[0.9375rem] font-semibold">
                        <span className="font-mono text-[0.6875rem] font-normal text-faint numeric">{String(i + 1).padStart(2, "0")}</span>
                        {stage.label}
                      </h3>
                      <span className="font-mono text-[0.6875rem] text-muted numeric">
                        {result ? (result.status === "skipped" ? "off" : formatDuration(result.duration_ms)) : ""}
                      </span>
                    </div>
                    <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">{stage.does}</p>
                    {stage.never && <p className="mt-1 text-[0.75rem] leading-relaxed text-muted">{stage.never}</p>}
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------- Verification band */}
      <section className="theme-dark border-y border-line bg-surface text-ink">
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 gap-12 px-4 py-24 sm:px-6 lg:grid-cols-2 lg:gap-20 lg:py-32">
          <div>
            <h2 className="text-[clamp(1.9rem,3.4vw,2.8rem)] font-[640] leading-[1.08] tracking-[-0.03em] [font-stretch:112%]">
              Models may explain. They may not invent.
            </h2>
            <p className="mt-5 max-w-[60ch] text-[1.0625rem] leading-[1.7] text-ink-soft">
              The model sees only fenced evidence, with secrets masked and prompt-injection text withheld. It must cite
              evidence IDs for every claim. Its output then passes through a verifier that rejects the claim outright, never
              repairing it, when any check fails.
            </p>
            <p className="mt-5 max-w-[60ch] text-[1.0625rem] leading-[1.7] text-ink-soft">
              Architecture does the rest: model output can add an explanation or a capped, separately labelled risk. It
              cannot delete, downgrade, or rewrite what the rules found.
            </p>
          </div>
          <ul className="grid content-start gap-px overflow-hidden rounded-[14px] border border-line bg-line">
            {[
              ["Evidence exists", "Every cited ID must be one ChangeGuard produced for this change."],
              ["Paths are real", "File paths mentioned must belong to the change or its evidence."],
              ["Lines are in range", "Line numbers must fall within the evidence the claim cites."],
              ["Symbols are attributed", "A function named in a claim must appear in the evidence it cites."],
              ["No invented numbers", "Percentages must appear in the evidence; coverage is never estimated."],
              ["No test results", "ChangeGuard runs no tests, so claims that tests passed or failed are rejected."],
            ].map(([title, body]) => (
              <li key={title} className="grid grid-cols-[28px_1fr] gap-3 bg-surface px-5 py-4">
                <span className="mt-0.5 flex size-5 items-center justify-center rounded-full border border-signal-glow/60 text-[0.6875rem] text-signal-glow" aria-hidden="true">
                  ✓
                </span>
                <span>
                  <span className="block text-[0.9375rem] font-semibold">{title}</span>
                  <span className="mt-0.5 block text-[0.8125rem] leading-relaxed text-muted">{body}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* --------------------------------------------------------- Evaluation */}
      <section className="border-b border-line">
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 gap-12 px-4 py-24 sm:px-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)] lg:gap-20 lg:py-32">
          <div>
            <h2 className="text-[clamp(1.9rem,3.4vw,2.8rem)] font-[640] leading-[1.08] tracking-[-0.03em] [font-stretch:112%]">
              Measured on labelled changes, including the ones it misses.
            </h2>
            <p className="prose-lab mt-5">
              {evaluation.manifest.cases} code changes with {evaluation.manifest.labels} hand-written labels and{" "}
              {evaluation.manifest.negative_controls} negative controls, compared against two naive baselines. Two holdout sets
              were written only after the rules were frozen, and each was run once before anything changed.
            </p>
            {cleanRuns.length > 0 && (
              <div className="mt-8 rounded-[12px] border border-line">
                <p className="border-b border-line px-5 py-3 text-xs text-muted">Clean holdout results: first run of each set</p>
                <table className="w-full text-left text-[0.8125rem]">
                  <thead>
                    <tr className="text-[0.6875rem] text-muted">
                      <th scope="col" className="px-5 pb-1 pt-3 font-medium">Set</th>
                      <th scope="col" className="px-2 pb-1 pt-3 text-right font-medium">Precision</th>
                      <th scope="col" className="px-2 pb-1 pt-3 text-right font-medium">Recall</th>
                      <th scope="col" className="px-5 pb-1 pt-3 text-right font-medium">False alarms on safe changes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cleanRuns.map((run) => (
                      <tr key={run.split}>
                        <th scope="row" className="px-5 py-1.5 font-normal text-ink-soft">
                          {run.split === "holdout" ? "Holdout" : "Holdout v2"} <span className="text-faint">· {run.cases} cases</span>
                        </th>
                        <td className="px-2 py-1.5 text-right font-semibold numeric">{formatPercent(run.precision)}</td>
                        <td className="px-2 py-1.5 text-right font-semibold numeric">{formatPercent(run.recall)}</td>
                        <td className="px-5 py-1.5 text-right font-semibold numeric">{formatPercent(run.negative_fp_rate, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="px-5 pb-4 pt-2 text-xs leading-relaxed text-muted">
                  Small and synthetic: these numbers show consistency with the labelling guide, not real-world effectiveness.
                </p>
              </div>
            )}
            <ButtonLink href="/evaluation" variant="secondary" className="mt-8">
              Full evaluation
            </ButtonLink>
          </div>
          <Figure
            number="2"
            caption={
              <>
                Precision and recall on all {evaluation.manifest.cases} cases, with 95% bootstrap intervals over cases (
                {evaluation.manifest.bootstrap.samples.toLocaleString()} resamples). The diff-only row is the same engine without a
                repository snapshot. Evidence integrity: {primary?.evidence.unsupported_findings ?? 0} of{" "}
                {primary?.evidence.findings_checked ?? 0} findings cited evidence that failed an independent re-check.
              </>
            }
          >
            <div className="grid grid-cols-1 gap-10 rounded-[14px] border border-line p-6 sm:grid-cols-2">
              <CIChart title="Precision" rows={rows("precision")} />
              <CIChart title="Recall" rows={rows("recall")} />
            </div>
          </Figure>
        </div>
      </section>

      {/* ------------------------------------------------------------ Never */}
      <section>
        <div className="mx-auto max-w-[1240px] px-4 py-24 sm:px-6 lg:py-32">
          <h2 className="max-w-2xl text-[clamp(1.9rem,3.4vw,2.8rem)] font-[640] leading-[1.08] tracking-[-0.03em] [font-stretch:112%]">
            Six things ChangeGuard will never do.
          </h2>
          <ul className="mt-12 grid gap-x-12 gap-y-0 md:grid-cols-2">
            {[
              ["Run your code.", "Uploads are parsed, never executed. Git is invoked with hooks and external diff drivers disabled."],
              ["Send a secret to a model.", "Detected credentials are masked before any report, export, or prompt is built."],
              ["Let a model overrule a rule.", "AI output is additive and capped at medium confidence. It cannot remove a finding."],
              ["Dress a heuristic as a fact.", "Every finding carries its provenance, and severity is kept separate from confidence."],
              ["Invent a probability.", "No blended risk score. The review priority is a transparent rule over labelled findings."],
              ["Keep your repository.", "Archives are read in memory and discarded; reports store only the excerpts they cite."],
            ].map(([title, body]) => (
              <li key={title} className="flex gap-5 border-t border-line py-6">
                <span className="mt-1.5 size-2 shrink-0 rotate-45 bg-signal" aria-hidden="true" />
                <span>
                  <span className="block text-lg font-semibold tracking-[-0.01em]">{title}</span>
                  <span className="mt-1 block text-[0.9375rem] leading-relaxed text-ink-soft">{body}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* -------------------------------------------------------------- CTA */}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 items-center gap-12 px-4 py-24 sm:px-6 lg:grid-cols-2 lg:gap-20">
          <div>
            <h2 className="display text-[clamp(2.2rem,4.4vw,3.6rem)]">Run it on your next pull request.</h2>
            <p className="prose-lab mt-6">
              Start the engine and the web app with one command, or use the CLI as a CI gate that emits SARIF for code
              scanning. Local models via Ollama are optional; nothing requires a paid API.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="/analyze" size="lg">
                Analyse a diff
              </ButtonLink>
              <ButtonLink href="/experience" size="lg" variant="secondary">
                See how it works
              </ButtonLink>
            </div>
          </div>
          <div className="space-y-4">
            <CodeBlock title="Local, with Docker" lang="bash" code={"docker compose up\n# web: http://localhost:3000   engine: http://localhost:8000/api/docs"} />
            <CodeBlock
              title="As a CI gate"
              lang="bash"
              code={"changeguard analyze --git-repo . --base origin/main \\\n  --format sarif --output changeguard.sarif --fail-on high"}
            />
          </div>
        </div>
      </section>
    </>
  );
}
