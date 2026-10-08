import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { ExperienceShell } from "@/components/experience/experience-shell";
import { Plate } from "@/components/experience/plate";
import { RuleCatalog } from "@/components/method/rule-catalog";
import { ProvenanceBadge } from "@/components/ui/badges";
import { Figure } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { isAISystem } from "@/lib/eval-format";
import { formatPercent, PRIORITY_META } from "@/lib/format";
import { STAGES } from "@/lib/stages";
import { evaluation, rules, sampleReport, sampleReportAI } from "@/lib/static-data";

export const metadata: Metadata = {
  title: "Method and system card",
  description:
    "How ChangeGuard works, every rule it can report, the AI system card, the threat model, data handling, and known limitations.",
};

const SECTIONS = [
  { id: "use", n: "1", title: "Intended use" },
  { id: "architecture", n: "2", title: "Architecture" },
  { id: "provenance", n: "3", title: "Findings and provenance" },
  { id: "rules", n: "4", title: "Rule catalogue" },
  { id: "ai", n: "5", title: "AI system card" },
  { id: "security", n: "6", title: "Threat model" },
  { id: "data", n: "7", title: "Data handling" },
  { id: "limitations", n: "8", title: "Limitations" },
];

function Section({ id, n, title, heading, children }: { id: string; n: string; title: string; heading: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-32 border-t border-line py-16 sm:py-20 lg:scroll-mt-24">
      <p className="font-mono text-[0.6875rem] text-muted">
        <span className="mr-2 inline-flex h-5 min-w-6 items-center justify-center rounded-[5px] bg-ink px-1.5 font-semibold text-bg">{n}</span>
        {title}
      </p>
      <h2 id={`${id}-title`} className="mt-4 max-w-[26ch] text-[clamp(1.65rem,2.9vw,2.35rem)] font-[640] leading-[1.12] tracking-[-0.027em] [font-stretch:112%]">
        {heading}
      </h2>
      {children}
    </section>
  );
}

function Prose({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("prose-lab mt-6 space-y-4", className)}>{children}</div>;
}

function Box({ title, children, tone = "neutral", className }: { title: string; children: ReactNode; tone?: "neutral" | "ai" | "signal"; className?: string }) {
  return (
    <div
      className={cn(
        "rounded-[10px] border px-3 py-2.5",
        tone === "ai" ? "border-ai/40 bg-ai-tint" : tone === "signal" ? "border-signal/40 bg-signal-tint" : "border-line-strong bg-bg",
        className,
      )}
    >
      <p className="text-[0.75rem] font-semibold text-ink">{title}</p>
      <div className="mt-0.5 text-[0.6875rem] leading-relaxed text-muted">{children}</div>
    </div>
  );
}

function Arrow({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center justify-center text-faint", className)} aria-hidden="true">
      <svg viewBox="0 0 24 24" className="size-4 rotate-90 lg:rotate-0">
        <path d="M4 12h15m-5-5 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

const THREATS: { threat: string; mitigation: string }[] = [
  {
    threat: "A hostile archive: path traversal, symlinks, decompression bombs, millions of members",
    mitigation:
      "Read in memory, never extracted. Absolute paths, `..`, drive letters and NUL bytes are rejected; links and devices are ignored; member count, per-file size and decompressed bytes are capped on bytes actually read; suspicious compression ratios are refused.",
  },
  {
    threat: "A malformed or adversarial patch",
    mitigation: "Strict parser with size, line and file limits. Absolute and parent-relative paths are rejected. Stray content after a hunk is an error, not something to skip.",
  },
  {
    threat: "XML attacks in coverage reports (entity expansion, external entities)",
    mitigation: "Cobertura is parsed with defusedxml under a size limit.",
  },
  {
    threat: "Code execution through the analysed repository: hooks, build scripts, linter configuration",
    mitigation:
      "Nothing from the repository runs. Ruff reads source through stdin with repository configuration ignored, no cache, a minimal environment and a timeout. The CLI's git mode disables hooks, external diff drivers and fsmonitor.",
  },
  {
    threat: "Prompt injection hidden in code or comments",
    mitigation:
      "A rule flags instruction-like text; flagged lines are withheld from the model; every excerpt is fenced as untrusted data; model output is parsed as data and never triggers an action.",
  },
  {
    threat: "Secrets in the change",
    mitigation: "Detected credentials are masked before a report, export or prompt is built, and are never sent to a model provider.",
  },
  {
    threat: "Model hallucination presented as analysis",
    mitigation: "A closed schema without location fields, a grounding verifier that rejects rather than repairs, and a separate, capped lane for model findings.",
  },
  {
    threat: "Abuse of an exposed API",
    mitigation:
      "Optional API keys compared in constant time, a per-client sliding-window rate limit, request body limits, a per-analysis timeout, and a cap on stored analyses.",
  },
  {
    threat: "Script injection into the web UI from analysed content",
    mitigation:
      "Untrusted text is rendered as React text nodes, never HTML; syntax highlighting produces token spans. The site sends a same-origin Content Security Policy and refuses framing.",
  },
  {
    threat: "Leaking the engine credentials to browsers",
    mitigation: "The web app proxies the API on its own origin and adds the engine key server-side; the key never reaches the browser.",
  },
];

function renderCode(text: string): ReactNode[] {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2 ? (
      <code key={i} className="rounded bg-surface-2 px-1 font-mono text-[0.86em] text-ink">
        {part.slice(1, -1)}
      </code>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export default function MethodPage() {
  const ai = sampleReportAI.ai;
  const aiSystems = evaluation.systems.filter((s) => isAISystem(s.system));
  const deterministic = rules.filter((r) => r.kind === "deterministic").length;
  const heuristic = rules.filter((r) => r.kind === "heuristic").length;
  const ruff = rules.filter((r) => r.source === "ruff").length;
  const own = rules.length - ruff;
  const engineLimitations = sampleReport.limitations;

  return (
    <>
      <header className="mx-auto max-w-[1240px] px-4 pb-12 pt-14 sm:px-6 lg:pt-20">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-muted">
          <span>Method and system card</span>
          <span className="text-faint" aria-hidden="true">·</span>
          <span>
            engine {sampleReport.engine_version} · ruleset {sampleReport.ruleset_version} · report schema {sampleReport.schema_version}
          </span>
        </p>
        <h1 className="display mt-5 max-w-[18ch] text-[clamp(2.3rem,4.6vw,3.9rem)]">How it works, what it checks, and where it stops.</h1>
        <p className="prose-lab mt-6 text-[1.125rem]">
          This page documents the engine the way a system card documents a model: what it is for, how it is built, every rule
          it can report, how the optional language model is constrained, what it defends against, what it stores, and what it
          cannot do.
        </p>
      </header>

      <ExperienceShell chapters={SECTIONS.map((s) => ({ id: s.id, n: s.n, title: s.title }))} heading="Contents">
        {/* ------------------------------------------------------------- 1 Use */}
        <Section id="use" n="1" title="Intended use" heading="A second reader for code review, not a gate on its own.">
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            <div className="rounded-[12px] border border-line p-5">
              <p className="text-[0.875rem] font-semibold text-ink">Designed for</p>
              <ul className="mt-3 space-y-2 text-[0.875rem] leading-relaxed text-ink-soft">
                {[
                  "Pointing reviewers at the lines of a change most likely to need attention, with the evidence for each.",
                  "Catching mechanical breakage before review: callers that no longer bind, removed symbols still referenced, new lint errors.",
                  "Showing which changed lines no test executed, from a coverage report you already produce.",
                  "Gating CI on deterministic and heuristic findings above a chosen severity.",
                ].map((item) => (
                  <li key={item} className="flex gap-2.5">
                    <span className="mt-[0.6em] size-1.5 shrink-0 rotate-45 bg-ok" aria-hidden="true" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-[12px] border border-line p-5">
              <p className="text-[0.875rem] font-semibold text-ink">Not designed for</p>
              <ul className="mt-3 space-y-2 text-[0.875rem] leading-relaxed text-ink-soft">
                {[
                  "Deciding whether a change is safe to ship. An empty report means no rule matched, not that the change is correct.",
                  "Estimating the probability of a production incident. No score here is a probability.",
                  "Replacing tests, type checkers, or human review of meaning: semantic regressions are its weakest category.",
                  "Analysing languages without structural support beyond the text-level rules (secrets, migrations, dependencies).",
                ].map((item) => (
                  <li key={item} className="flex gap-2.5">
                    <span className="mt-[0.6em] size-1.5 shrink-0 rotate-45 bg-danger" aria-hidden="true" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Section>

        {/* ---------------------------------------------------- 2 Architecture */}
        <Section id="architecture" n="2" title="Architecture" heading="One pipeline, four ways in, nothing executed.">
          <Prose>
            <p>
              ChangeGuard is a modular monolith: a Python engine (FastAPI, tree-sitter, Ruff) with a SQLite store, a Next.js web
              app that proxies the engine on its own origin, and a CLI that runs the same pipeline in CI. Every analysis goes
              through the same eleven stages, each reporting its status, timing and a structured summary.
            </p>
          </Prose>
          <Figure number="1" className="mt-8" caption="System overview. Dashed outlines are trust boundaries: everything inside the engine treats inputs as untrusted data, and the model zone can only return claims for verification.">
            <div className="rounded-[14px] border border-line bg-surface p-4 sm:p-6">
              <div className="grid items-stretch gap-3 lg:grid-cols-[minmax(0,0.9fr)_24px_minmax(0,2.4fr)_24px_minmax(0,0.9fr)]">
                {/* Inputs */}
                <div className="rounded-[12px] border border-dashed border-danger/50 p-3">
                  <p className="mb-2 font-mono text-[0.625rem] text-danger">untrusted inputs</p>
                  <div className="space-y-2">
                    <Box title="Patch">git or plain unified diff</Box>
                    <Box title="Snapshot">zip or tar of the base revision</Box>
                    <Box title="Coverage">Cobertura, LCOV, coverage.py JSON</Box>
                  </div>
                </div>
                <Arrow />
                {/* Engine */}
                <div className="rounded-[12px] border border-dashed border-line-strong p-3">
                  <p className="mb-2 font-mono text-[0.625rem] text-muted">engine · parsed, never executed</p>
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {STAGES.filter((s) => !["synthesis", "verification"].includes(s.name)).map((stage, i) => (
                      <Box key={stage.name} title={`${String(i + 1).padStart(2, "0")} ${stage.label}`}>
                        {stage.does}
                      </Box>
                    ))}
                  </div>
                  <div className="mt-3 rounded-[10px] border border-dashed border-ai/50 p-2.5">
                    <p className="mb-2 font-mono text-[0.625rem] text-ai">optional model zone · claims only</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {STAGES.filter((s) => ["synthesis", "verification"].includes(s.name)).map((stage) => (
                        <Box key={stage.name} title={stage.label} tone="ai">
                          {stage.does}
                        </Box>
                      ))}
                    </div>
                  </div>
                </div>
                <Arrow />
                {/* Surfaces */}
                <div className="rounded-[12px] border border-line p-3">
                  <p className="mb-2 font-mono text-[0.625rem] text-muted">surfaces</p>
                  <div className="space-y-2">
                    <Box title="Report JSON">schema {sampleReport.schema_version}, stored in SQLite</Box>
                    <Box title="REST API + SSE">progress streamed per stage</Box>
                    <Box title="Web app">same-origin proxy holds the key</Box>
                    <Box title="CLI">Markdown, SARIF, JSON, exit codes</Box>
                  </div>
                </div>
              </div>
            </div>
          </Figure>
          <div className="mt-8 grid gap-x-10 gap-y-5 md:grid-cols-2">
            {[
              ["Two revisions, rebuilt in memory", "The patch is applied to the snapshot to recover both sides. Without a snapshot, analysis falls back to a diff-only mode that parses hunks as fragments and says so in the report."],
              ["Structure before text", "Python, JavaScript, TypeScript and TSX are parsed with tree-sitter into symbols, signatures, imports and calls. Line-level rules handle everything else."],
              ["Differential by default", "Ruff and the pattern rules only report what the change introduced. Pre-existing problems are never blamed on it."],
              ["Every stage is observable", "Stage results, timings and structured summaries are part of the report and stream to the browser as server-sent events."],
            ].map(([title, body]) => (
              <div key={title} className="border-t border-line pt-4">
                <p className="text-[0.875rem] font-semibold text-ink">{title}</p>
                <p className="mt-1 text-[0.875rem] leading-relaxed text-ink-soft">{body}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* ------------------------------------------------------ 3 Provenance */}
        <Section id="provenance" n="3" title="Findings and provenance" heading="Three kinds of finding, never blended.">
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {(
              [
                ["deterministic", "Established by analysis of your inputs: a parse, a resolved call, a measured line. Evidence is the proof."],
                ["heuristic", "Inferred by a rule. Worth a reviewer's attention; impact depends on context, so confidence is stated explicitly."],
                ["ai", "Proposed by a model and kept only after verification. Confidence capped at medium; never fails a build."],
              ] as const
            ).map(([kind, body]) => (
              <div key={kind} className="rounded-[12px] border border-line p-4">
                <ProvenanceBadge kind={kind} />
                <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink-soft">{body}</p>
              </div>
            ))}
          </div>
          <Prose>
            <p>
              <strong>Severity</strong> (critical, high, medium, low, info) is how bad the problem would be if real.{" "}
              <strong>Confidence</strong> (high, medium, low) is how sure the rule is that it is real. They are separate
              categorical judgements defined per rule. Neither is a probability, and they are never multiplied into a score.
            </p>
            <p>
              Every finding cites evidence by ID (E1, E2, …): a diff hunk, a call site, a diagnostic, a coverage measurement.
              Finding IDs are derived from rule and location, so the same change yields the same IDs on every run.
            </p>
          </Prose>
          <div className="mt-8 overflow-hidden rounded-[12px] border border-line">
            <p className="border-b border-line bg-surface px-4 py-2.5 text-[0.75rem] font-medium text-muted">
              Review priority: the first rule that matches, top to bottom
            </p>
            <ol className="divide-y divide-line">
              {[
                ["block", "A critical finding established by deterministic analysis."],
                ["high", "Any high-severity deterministic or heuristic finding."],
                ["elevated", "Any medium-severity finding. AI findings alone can raise priority this far and no further."],
                ["routine", "Only low-severity or informational findings."],
              ].map(([level, rule]) => (
                <li key={level} className="grid grid-cols-[96px_minmax(0,1fr)] gap-4 px-4 py-2.5 text-[0.8125rem]">
                  <span className="font-semibold text-ink">{PRIORITY_META[level]?.label}</span>
                  <span className="text-ink-soft">{rule}</span>
                </li>
              ))}
            </ol>
          </div>
        </Section>

        {/* ----------------------------------------------------------- 4 Rules */}
        <Section id="rules" n="4" title="Rule catalogue" heading={`${rules.length} rules, each with a stated rationale.`}>
          <Prose>
            <p>
              {own} rules are ChangeGuard&rsquo;s own; {ruff} are curated Ruff rules run differentially on Python files.{" "}
              {deterministic} are deterministic and {heuristic} heuristic. Severities shift with context where the rule says
              so: a changed default value is medium when callers rely on it or the function is public and low otherwise, and a
              removed symbol is critical when other files still import it. Findings link here from their rule ID.
            </p>
          </Prose>
          <div className="mt-8">
            <RuleCatalog rules={rules} />
          </div>
        </Section>

        {/* -------------------------------------------------------------- 5 AI */}
        <Section id="ai" n="5" title="AI system card" heading="An optional model, held to the evidence.">
          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <Plate label="configuration" bodyClassName="divide-y divide-line text-[0.8125rem]">
              {[
                ["Default", "Off. Reports are complete without a model."],
                ["Local", "Ollama (e.g. llama3.2:3b, qwen2.5-coder:7b): no API key, no data leaves the machine."],
                ["Compatible", "Any OpenAI-compatible endpoint, such as vLLM or LM Studio. Tested against a mocked server only."],
                ["Hosted", "Claude API with structured outputs (claude-opus-5-5 by default); opt-in, needs a key. Tested against a mocked client only."],
                ["Decoding", "Temperature 0 and a fixed seed where the provider supports them; optional k-sample voting."],
                ["Context", "Up to 8 findings and 24,000 characters of fenced, redacted evidence per change."],
              ].map(([k, v]) => (
                <div key={k} className="grid grid-cols-[96px_minmax(0,1fr)] gap-3 px-4 py-2.5">
                  <span className="text-muted">{k}</span>
                  <span className="text-ink-soft">{v}</span>
                </div>
              ))}
            </Plate>
            <Plate label="invariants · enforced in code" bodyClassName="p-4">
              <ul className="space-y-2 text-[0.8125rem] leading-relaxed text-ink-soft">
                {[
                  "Cannot delete, downgrade, or rewrite a rule's finding; notes appear beside it.",
                  "Every claim must cite evidence IDs, and is verified before display.",
                  "Model-proposed risks have no location fields; location comes from the cited evidence.",
                  "Model risks: confidence at most medium, priority at most elevated, never counted by --fail-on.",
                  "Free-text summaries cannot be verified claim by claim and are never displayed as analysis.",
                  "Secrets are masked and injection-like lines withheld before the prompt is built.",
                  "Model output is never executed, and suggested test code is never run.",
                ].map((item) => (
                  <li key={item} className="flex gap-2.5">
                    <svg viewBox="0 0 16 16" className="mt-[3px] size-3.5 shrink-0 text-ok" aria-hidden="true">
                      <path d="M3.5 8.4 6.6 11.4 12.6 4.8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span>{renderCode(item)}</span>
                  </li>
                ))}
              </ul>
            </Plate>
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Plate label="traceability" bodyClassName="divide-y divide-line font-mono text-[0.6875rem]">
              {[
                ["prompt", `${ai.prompt_id ?? "review"} v${ai.prompt_version ?? "?"}`],
                ["prompt sha256", ai.prompt_sha256 ?? "—"],
                ["per call", "request sha256, latency, tokens, attempts, cache hit"],
                ["cache", "responses keyed by request fingerprint (SQLite)"],
                ["evaluation", "record / replay cassettes per fingerprint"],
              ].map(([k, v]) => (
                <div key={k} className="grid grid-cols-[112px_minmax(0,1fr)] gap-3 px-4 py-2">
                  <span className="text-muted">{k}</span>
                  <span className="break-all text-ink-soft">{v}</span>
                </div>
              ))}
            </Plate>
            <Plate label="measured · labelled dataset" bodyClassName="p-4">
              <ul className="space-y-2.5 text-[0.8125rem]">
                {aiSystems.map((s) => (
                  <li key={s.system} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
                    <span className="font-mono text-[0.75rem] text-ink">{s.system.replace("changeguard+ai:", "")}</span>
                    <span className="text-[0.75rem] text-muted">
                      precision <span className="font-mono text-ink numeric">{formatPercent(s.overall.precision)}</span> · false alarms{" "}
                      <span className="font-mono text-ink numeric">{formatPercent(s.negative_controls.false_positive_rate, 0)}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 border-t border-line pt-3 text-[0.75rem] leading-relaxed text-muted">
                Grounding held for every model: no unsupported evidence. Larger models proposed more risks, most matching no
                label. Explanation quality has not been rated by people.{" "}
                <Link href="/evaluation#ai" className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal">
                  Full results
                </Link>
                .
              </p>
            </Plate>
          </div>
          <div className="mt-6 rounded-[12px] border border-line p-5">
            <p className="text-[0.875rem] font-semibold text-ink">Known failure modes</p>
            <ul className="mt-3 grid gap-x-8 gap-y-2 text-[0.8125rem] leading-relaxed text-ink-soft md:grid-cols-2">
              {[
                "Misattribution in free text: a recorded summary put a condition change in the wrong function. Such text stays in the trace only.",
                "Plausible but wrong risks: grounded claims that cite real evidence yet describe a problem that is not there.",
                "Context truncation: large changes are trimmed to the budget, so the model may not see every finding.",
                "Provider variance: hosted models change over time; recorded responses make evaluation reproducible, not live behaviour.",
              ].map((item) => (
                <li key={item} className="flex gap-2.5">
                  <span className="mt-[0.6em] size-1.5 shrink-0 rotate-45 bg-signal" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </Section>

        {/* -------------------------------------------------------- 6 Security */}
        <Section id="security" n="6" title="Threat model" heading="Everything it reads is treated as hostile.">
          <Prose>
            <p>
              Patches, archives, coverage reports, and the code inside them are attacker-controlled. The table lists each threat
              considered and the mitigation in place. Deployment guidance, including putting the web app behind access control
              when it should not be public, is in <code>docs/SECURITY.md</code>.
            </p>
          </Prose>
          <div className="mt-8 overflow-hidden rounded-[12px] border border-line">
            <div className="hidden grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)] gap-6 border-b border-line bg-surface px-4 py-2.5 text-[0.6875rem] font-medium text-muted md:grid">
              <span>Threat</span>
              <span>Mitigation</span>
            </div>
            <ul className="divide-y divide-line">
              {THREATS.map((t) => (
                <li key={t.threat} className="grid gap-x-6 gap-y-1 px-4 py-3 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)]">
                  <span className="text-[0.8125rem] font-medium text-ink">{t.threat}</span>
                  <span className="text-[0.8125rem] leading-relaxed text-ink-soft">{renderCode(t.mitigation)}</span>
                </li>
              ))}
            </ul>
          </div>
        </Section>

        {/* ------------------------------------------------------------ 7 Data */}
        <Section id="data" n="7" title="Data handling" heading="What is kept, where, and for how long.">
          <div className="mt-8 grid gap-x-10 gap-y-5 md:grid-cols-2">
            {[
              ["Stored", "Each analysis: its report (the diff hunks, cited excerpts, findings and stage results), the patch's SHA-256, options and progress events, in the engine's SQLite database. With AI enabled, model responses are cached there by request fingerprint."],
              ["Not stored", "The uploaded archive, the coverage file, and the full repository. They are read in memory and discarded when the analysis ends."],
              ["Masked", "Detected secrets are masked in everything stored, exported, or sent to a model."],
              ["Retention", "Analyses are deleted on request from the Reports page or the API. The store keeps the 500 most recent by default."],
              ["Model providers", "With a hosted model enabled, the redacted evidence pack is sent to that provider and its data policy applies. Local models keep everything on the machine."],
              ["Telemetry", "None at runtime: neither the engine nor the web app calls out except to a model provider you configure. Fonts are bundled at build time, and the provided images disable Next.js build telemetry."],
            ].map(([title, body]) => (
              <div key={title} className="border-t border-line pt-4">
                <p className="text-[0.875rem] font-semibold text-ink">{title}</p>
                <p className="mt-1 text-[0.875rem] leading-relaxed text-ink-soft">{body}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* ----------------------------------------------------- 8 Limitations */}
        <Section id="limitations" n="8" title="Limitations" heading="Known limits of the engine.">
          <ol className="mt-8 space-y-4">
            {[
              ...engineLimitations,
              "Structural analysis covers Python, JavaScript, TypeScript and TSX. Other languages get line-level rules only.",
              "Coverage numbers are only as current as the uploaded report; a plausibility check lowers confidence when it looks stale, but cannot prove it fresh.",
              "Evaluation uses a small synthetic dataset written by the same author as the rules; see the evaluation for what that implies.",
            ].map((text, i) => (
              <li key={text} className="grid max-w-[78ch] grid-cols-[28px_minmax(0,1fr)] gap-3 text-[0.9375rem] leading-relaxed text-ink-soft">
                <span className="font-mono text-[0.75rem] text-muted numeric">{String(i + 1).padStart(2, "0")}</span>
                <span>{text}</span>
              </li>
            ))}
          </ol>
        </Section>
      </ExperienceShell>
    </>
  );
}
