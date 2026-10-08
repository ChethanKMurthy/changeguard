import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { CodeBlock } from "@/components/code/code";
import { ExperienceShell, type ChapterLink } from "@/components/experience/experience-shell";
import { FigAI } from "@/components/experience/fig-ai";
import { FigCallers } from "@/components/experience/fig-callers";
import { FigCoverage } from "@/components/experience/fig-coverage";
import { FigDiff } from "@/components/experience/fig-diff";
import { FigInputs } from "@/components/experience/fig-inputs";
import { FigLint } from "@/components/experience/fig-lint";
import { FigMatrix } from "@/components/experience/fig-matrix";
import { FigRules } from "@/components/experience/fig-rules";
import { FigSymbols } from "@/components/experience/fig-symbols";
import { Plate, StageTag } from "@/components/experience/plate";
import { RunConsole } from "@/components/experience/run-console";
import { ButtonLink } from "@/components/ui/button";
import { Figure } from "@/components/ui/primitives";
import { experienceData } from "@/lib/experience-data";
import { formatDuration } from "@/lib/format";
import { sampleExports } from "@/lib/static-data";

export const metadata: Metadata = {
  title: "Guided experience",
  description:
    "Follow one code change through every stage of ChangeGuard: reconstruction, structural diff, caller checks, differential lint, risk rules, coverage, AI verification, and the report.",
};

function Chapter({
  id,
  n,
  stages,
  title,
  children,
}: {
  id: string;
  n: string;
  stages: { label: string; ms?: number | null }[];
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-32 border-t border-line py-16 sm:py-20 lg:scroll-mt-24">
      <StageTag n={n} stages={stages} />
      <h2 id={`${id}-title`} className="mt-4 max-w-[24ch] text-[clamp(1.75rem,3.1vw,2.5rem)] font-[640] leading-[1.1] tracking-[-0.028em] [font-stretch:112%]">
        {title}
      </h2>
      <div className="mt-6 space-y-8">{children}</div>
    </section>
  );
}

function Prose({ children }: { children: ReactNode }) {
  return <div className="prose-lab space-y-4">{children}</div>;
}

function Caveat({ title, children }: { title: string; children: ReactNode }) {
  return (
    <aside className="grid max-w-[72ch] grid-cols-[20px_minmax(0,1fr)] gap-3 rounded-[10px] border border-line bg-surface p-4">
      <span className="mt-0.5 flex size-5 items-center justify-center rounded-full border border-line-strong font-mono text-[0.625rem] font-semibold text-muted" aria-hidden="true">
        i
      </span>
      <div className="text-[0.875rem] leading-relaxed text-ink-soft [&_code]:rounded [&_code]:bg-surface-2 [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[0.86em] [&_code]:text-ink">
        <p className="font-semibold text-ink">{title}</p>
        <div className="mt-1 space-y-2">{children}</div>
      </div>
    </aside>
  );
}

function ms(...values: (number | undefined)[]) {
  const total = values.reduce<number>((sum, v) => sum + (v ?? 0), 0);
  return total;
}

function C({ children }: { children: ReactNode }) {
  return <code>{children}</code>;
}

export default function ExperiencePage() {
  const d = experienceData();
  const r = d.report;
  const s = r.summary;
  const t = d.stageMs;
  const aiT = d.aiStageMs;
  const breaking = d.callers.symbols.find((x) => x.breaking);
  const compatibleSig = d.callers.symbols.find((x) => !x.breaking);
  const testFile = d.callers.incompatible.find((e) => e.file?.startsWith("tests/"));
  const merged = d.lint.findings.find((f) => f.corroborated_by.length > 0);
  const undefinedName = d.lint.findings.find((f) => f.rule_id === "RUFF-F821");
  const symbolsWithTests = d.coverage.symbols.filter((x) => x.tests > 0).length;
  const ruleHits = d.rules.families.filter((f) => f.count > 0).length;

  // The unchanged docstring above the flipped condition, read from the diff context.
  const logicSymbol = r.symbols.find((x) => x.qualname === r.findings.find((f) => f.rule_id === "CG-LOG-001")?.related_symbols[0]);
  const logicLine = d.rules.logicEvidence?.start_line ?? 0;
  const docLine = r.files
    .find((f) => f.path === d.rules.logicEvidence?.file)
    ?.hunks.flatMap((h) => h.lines)
    .find((l) => l.kind === "context" && l.new != null && logicSymbol?.start_line != null && l.new > logicSymbol.start_line && l.new < logicLine && l.content.trim().startsWith('"""'));
  const docstring = docLine?.new != null ? { line: docLine.new, text: docLine.content.trim() } : null;

  const chapters: (ChapterLink & { stages: { label: string; ms?: number | null }[] })[] = [
    { id: "change", n: "01", title: "The change", stages: [{ label: "Parse inputs", ms: t.ingest }, { label: "Reconstruct revisions", ms: t.workspace }] },
    { id: "structure", n: "02", title: "Structure", stages: [{ label: "Structural diff", ms: t.structure }] },
    { id: "callers", n: "03", title: "Callers", stages: [{ label: "Cross-file references", ms: t.references }] },
    { id: "static", n: "04", title: "Static analysis", stages: [{ label: "Static analysis", ms: t.static }] },
    { id: "rules", n: "05", title: "Risk rules", stages: [{ label: "Risk rules", ms: t.rules }] },
    { id: "coverage", n: "06", title: "Tests and coverage", stages: [{ label: "Test mapping", ms: t.tests }, { label: "Coverage", ms: t.coverage }] },
    { id: "ai", n: "07", title: "AI and verification", stages: [{ label: "AI synthesis", ms: aiT.synthesis }, { label: "Grounding verification", ms: aiT.verification }] },
    { id: "report", n: "08", title: "The report", stages: [{ label: "Assemble report", ms: t.report }] },
    { id: "ci", n: "09", title: "In your pipeline", stages: [{ label: "CLI and exports" }] },
  ];
  const rail = chapters.map((c) => {
    const total = c.stages.some((x) => x.ms != null) ? ms(...c.stages.map((x) => x.ms ?? undefined)) : null;
    return { id: c.id, n: c.n, title: c.title, time: total != null ? formatDuration(total) : null };
  });
  const stagesOf = (id: string) => chapters.find((c) => c.id === id)?.stages ?? [];

  return (
    <>
      {/* ------------------------------------------------------------ Header */}
      <header className="mx-auto max-w-[1240px] px-4 pb-14 pt-14 sm:px-6 lg:pt-20">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-muted">
          <span>Interactive walkthrough</span>
          <span className="text-faint" aria-hidden="true">·</span>
          <span>9 chapters</span>
          <span className="text-faint" aria-hidden="true">·</span>
          <span>
            engine {d.recorded.engine} · ruleset {d.recorded.ruleset}
          </span>
        </p>
        <h1 className="display mt-5 max-w-[17ch] text-[clamp(2.4rem,5vw,4.2rem)]">Follow one change through the engine.</h1>
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)] lg:gap-16">
          <p className="prose-lab text-[1.125rem]">
            A developer adds loyalty discounts to a billing service and switches price formatting from currency codes to
            locales. The diff is {s.additions + s.deletions} lines across {s.files_changed} files and reads like routine work.
            This page runs it through ChangeGuard one stage at a time and shows what each stage established, and how.
          </p>
          <div className="space-y-3 text-[0.875rem] leading-relaxed text-ink-soft">
            <p className="flex gap-2.5">
              <span className="mt-[0.55em] size-1.5 shrink-0 rotate-45 bg-signal" aria-hidden="true" />
              <span>
                <span className="font-semibold text-ink">The sample is synthetic.</span> A small repository written to exercise the
                analysers, labelled as such everywhere it appears.
              </span>
            </p>
            <p className="flex gap-2.5">
              <span className="mt-[0.55em] size-1.5 shrink-0 rotate-45 bg-signal" aria-hidden="true" />
              <span>
                <span className="font-semibold text-ink">The output is real.</span> Every number and finding below was produced by
                the engine. Run it yourself and the finding IDs should match.
              </span>
            </p>
          </div>
        </div>
        <Figure
          number="1"
          className="mt-12"
          caption="Run the bundled sample on your engine, or replay the recorded run. Stage times are measured; the reveal is paced so it can be followed."
        >
          <RunConsole sampleId={d.meta.id} recorded={d.recorded} inputs={d.inputs} />
        </Figure>
      </header>

      <ExperienceShell chapters={rail}>
        {/* ------------------------------------------------------ 01 The change */}
        <Chapter id="change" n="01" stages={stagesOf("change")} title="Three inputs, two revisions, nothing executed.">
          <Prose>
            <p>
              ChangeGuard accepts up to three inputs: the patch, a snapshot of the repository before the change, and a coverage
              report. All three are present here: a git patch touching {s.files_changed} files (+{s.additions} −{s.deletions}),
              a {d.inputs.snapshotFiles}-file snapshot, and a Cobertura report from the test suite.
            </p>
            <p>
              The patch is parsed strictly. A stray line after a hunk is an error, not something to skip. The parsed patch is
              then applied to the snapshot <strong>in memory</strong> to rebuild both revisions. Nothing is written to disk, no
              archive is extracted, and no script, hook, or test from the repository runs. Every later stage reads these two
              in-memory revisions.
            </p>
          </Prose>
          <Figure number="2" caption="Each file in the snapshot, what the patch does to it, and the head revision rebuilt from the two.">
            <FigInputs data={d.inputs} />
          </Figure>
          <Prose>
            <p>
              Before going further, read the diff yourself. Which lines would you stop at? When you have an answer, reveal what
              the engine flagged; the markers sit on the exact lines its findings point at.
            </p>
          </Prose>
          <Figure number="3" caption="The complete patch. Select a marker or a row to see the finding behind it.">
            <FigDiff files={r.files} findings={r.findings} />
          </Figure>
        </Chapter>

        {/* ---------------------------------------------------- 02 Structure */}
        <Chapter id="structure" n="02" stages={stagesOf("structure")} title={`${s.changed_symbols} symbols changed. ${s.breaking_symbols === 1 ? "One broke its contract." : `${s.breaking_symbols} broke their contracts.`}`}>
          <Prose>
            <p>
              A line diff knows which lines moved. It does not know that <C>format_price</C> is a function, that it had a
              defaulted <C>currency</C> parameter, or that the new version requires a <C>locale</C>. ChangeGuard parses both
              revisions with tree-sitter and compares them symbol by symbol: parameters, with their order, kinds and defaults,
              and return annotations.
            </p>
            {breaking && compatibleSig && (
              <p>
                Two signatures changed. <C>{compatibleSig.qualname}</C> gained a parameter with a default, so every existing
                call still binds. <C>{breaking.qualname}</C> lost <C>currency</C> and gained a required <C>locale</C>, and the
                structural diff marks it <strong>breaking</strong>. Whether that matters depends on who calls it, which is the
                next stage.
              </p>
            )}
          </Prose>
          <Figure number="4" caption="Changed symbols, with each signature change drawn parameter by parameter, and cyclomatic complexity before and after.">
            <FigSymbols symbols={r.symbols} />
          </Figure>
        </Chapter>

        {/* ------------------------------------------------------ 03 Callers */}
        <Chapter id="callers" n="03" stages={stagesOf("callers")} title="Every caller, checked the way Python binds arguments.">
          <Prose>
            <p>
              For each changed signature, ChangeGuard resolves imports across the snapshot to find the call sites. Here those
              are <C>from billing.pricing import …</C> in <C>invoice.py</C> and in the tests. It then replays each call against
              the new parameter list using Python&rsquo;s binding rules: positional slots, keywords, defaults,{" "}
              <C>*args</C> and <C>**kwargs</C>.
            </p>
            <p>
              {d.callers.checked} call sites were checked and {d.callers.incompatibleTotal} no longer bind. <C>render_line</C>{" "}
              passes <C>currency=</C>, a keyword the function no longer accepts, and a test calls <C>format_price</C> with no
              locale at all. Both would raise <C>TypeError</C> when they run. Together they make one deterministic,
              high-severity finding, with the call sites as its evidence.
            </p>
          </Prose>
          <Figure number="5" caption="Call sites of the two changed signatures. Select a failing call site to see the evidence the engine kept.">
            <FigCallers data={d.callers} />
          </Figure>
          {testFile && (
            <Caveat title="What a binding check cannot see">
              <p>
                Select the test call site in Fig. 5 and read the last line of its excerpt ({testFile.id}):{" "}
                <C>format_price(Decimal(&quot;5&quot;), &quot;EUR&quot;)</C>.
                It binds, because <C>&quot;EUR&quot;</C> lands in <C>locale</C>, so it is one of the compatible call sites. It is
                still wrong. The new lookup is keyed by locales like <C>en_US</C>, so <C>&quot;EUR&quot;</C> falls through to an
                empty symbol and the assertion would fail even after line {testFile.start_line} is fixed.
              </p>
              <p>Signature checks catch arity and keyword errors, not meaning. That part is still a reviewer&rsquo;s job.</p>
            </Caveat>
          )}
        </Chapter>

        {/* ----------------------------------------------- 04 Static analysis */}
        <Chapter id="static" n="04" stages={stagesOf("static")} title="Lint the change, not the codebase.">
          <Prose>
            <p>
              A linter run over a whole repository buries a reviewer in findings that predate the change. ChangeGuard runs Ruff
              on both revisions of each changed Python file and keeps only the diagnostics that are new in the head revision.
              Ruff reads the source through stdin with repository configuration ignored, so nothing in the repository can
              change how the tool behaves, and the analysed code is never executed.
            </p>
            {merged && (
              <p>
                {d.lint.diagnostics.length} diagnostics are new. Two of them, <C>E722</C> and <C>S110</C>, describe the same bare{" "}
                <C>except: pass</C> on line {merged.line}. The report merges them into one finding and records the second rule
                as corroboration instead of counting the problem twice.
              </p>
            )}
            {undefinedName && merged && (
              <p>
                Read the two pricing findings together. <C>REGIONAL_RATES</C> on line {undefinedName.line} is never defined, so
                the lookup raises <C>NameError</C>, and the bare <C>except</C> on the next line swallows it. Nothing crashes.
                Every non-EU invoice silently loses its regional tax.
              </p>
            )}
          </Prose>
          <Figure number="6" caption="New diagnostics in the head revision (left) and the findings they become after de-duplication (right).">
            <FigLint data={d.lint} />
          </Figure>
        </Chapter>

        {/* ---------------------------------------------------- 05 Risk rules */}
        <Chapter id="rules" n="05" stages={stagesOf("rules")} title="Rules that report what they checked, including when nothing was found.">
          <Prose>
            <p>
              Some risks have no linter: credentials pasted into code, text written to steer a language model, a migration that
              drops a column, a test whose assertions were deleted. ChangeGuard&rsquo;s rule set reads the added lines for these.
              {ruleHits === 1
                ? " On this change every family came back clear except one."
                : ` On this change ${ruleHits} of ${d.rules.families.length} families matched.`}
            </p>
            {docstring && (
              <p>
                <C>percent &gt; 50</C> became <C>percent &gt;= 50</C>. The docstring above it still says discounts{" "}
                <em>above</em> 50% need approval; now exactly 50% does too. Whether that is a fix or a regression is a business
                question, so the rule makes a <strong>heuristic</strong> finding with medium confidence, and the suggested check
                is a boundary-value test.
              </p>
            )}
          </Prose>
          <Figure number="7" caption="Each rule family and its number of matches on the added lines, then the one match with its context.">
            <FigRules data={d.rules} docstring={docstring} />
          </Figure>
        </Chapter>

        {/* ---------------------------------------------- 06 Tests & coverage */}
        <Chapter id="coverage" n="06" stages={stagesOf("coverage")} title="Which changed lines did any test ever run?">
          <Prose>
            <p>
              There are two independent signals here. Test mapping is static: it looks for test files that import a changed
              symbol&rsquo;s module and reference the symbol. {symbolsWithTests} of the {d.coverage.symbols.length} changed symbols
              have such tests. The others, including the new <C>loyalty_bonus</C> and the async handler, have none.
            </p>
            <p>
              Coverage is measured. The uploaded report records hit counts per line, and ChangeGuard intersects them with the
              changed lines of the head revision: {d.coverage.covered} of {d.coverage.executable} changed executable lines ran,
              which is {d.coverage.percent}% patch coverage. The report gets a plausibility check first. Hits on blank lines,
              comments, or lines past the end of a file mark it as stale, and that lowers the confidence of every coverage
              finding instead of being trusted at face value.
            </p>
          </Prose>
          <Figure number="8" caption="Left: tests found by static mapping. Right: every changed executable line, coloured by whether the uploaded coverage report says it ran.">
            <FigCoverage data={d.coverage} />
          </Figure>
        </Chapter>

        {/* ---------------------------------------------- 07 AI & verification */}
        <Chapter id="ai" n="07" stages={stagesOf("ai")} title="A model may explain. A verifier decides what you see.">
          <Prose>
            <p>
              With AI enabled, ChangeGuard sends a model a fenced evidence pack containing the findings, their evidence, and the
              changed code, with each excerpt wrapped as untrusted data. Secrets are masked before the pack is built, and any
              line that reads like an instruction to the model is withheld. The model must answer in a closed JSON schema in
              which every claim cites evidence IDs, and the schema has no file or line fields to fill in.
            </p>
            <p>
              The output then goes to a verifier. It rejects a claim outright, and never repairs it, if the claim cites
              evidence that does not exist, names a path outside the change, gives a line number outside the cited evidence,
              attributes a function the evidence does not contain, uses a number the evidence does not support, or reports a
              test result. ChangeGuard runs no tests, so no model may say one passed.
            </p>
            {d.ai.model && (
              <p>
                In the recorded run below, <C>{d.ai.model}</C>, running locally, made {d.ai.claims} claims and{" "}
                {d.ai.accepted} passed. One became a note on the call-site finding.
                {d.ai.assessmentIssue && (
                  <>
                    {" "}
                    It also wrote a free-text summary that puts the condition change in <C>{d.ai.assessmentIssue.claimed}</C>. The
                    change is in <C>{d.ai.assessmentIssue.actual}</C>. That summary is kept in the trace and never shown as
                    analysis.
                  </>
                )}
              </p>
            )}
          </Prose>
          <Figure
            number="9"
            caption={
              <>
                One recorded AI pass, from evidence pack to verified note. How much a model adds, and at what cost in false
                positives, is measured on the labelled dataset in the{" "}
                <Link href="/evaluation#ai" className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal">
                  evaluation
                </Link>
                .
              </>
            }
          >
            <FigAI data={d.ai} />
          </Figure>
        </Chapter>

        {/* ---------------------------------------------------- 08 The report */}
        <Chapter id="report" n="08" stages={stagesOf("report")} title={`${s.findings_total} findings, kept apart by how they were established.`}>
          <Prose>
            <p>
              Findings are de-duplicated, every evidence reference is checked to exist, and each finding gets a stable ID
              derived from its rule and location, so the same change produces the same IDs on every run. Severity and
              confidence are separate categorical judgements, defined per rule. They are not probabilities.
            </p>
            <p>
              The review priority is a written rule, not a score, and the figure lists it in full. Here{" "}
              {s.review_priority.triggered_by.length} high-severity deterministic findings set it to{" "}
              <strong>{s.review_priority.level}</strong>. A model&rsquo;s findings could never have pushed it past elevated.
            </p>
          </Prose>
          <Figure number="10" caption="Every finding, placed by severity and provenance. Ringed findings set the review priority.">
            <FigMatrix data={d.matrix} />
          </Figure>
          <div className="flex flex-wrap gap-3">
            <ButtonLink href="/reports/sample">Open the full report</ButtonLink>
            <ButtonLink href="/method#rules" variant="secondary">
              Read the rule catalogue
            </ButtonLink>
          </div>
        </Chapter>

        {/* --------------------------------------------------------- 09 CI */}
        <Chapter id="ci" n="09" stages={stagesOf("ci")} title="The same engine in CI, gating only on what it can show.">
          <Prose>
            <p>
              The CLI runs the identical pipeline on a git range. It writes Markdown for a pull-request comment, SARIF for code
              scanning, or the full JSON report, and it can fail the build at a severity threshold. AI findings never fail a
              build. Only deterministic and heuristic findings count.
            </p>
          </Prose>
          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
            <CodeBlock
              title="CI step"
              lang="bash"
              code={[
                "changeguard analyze \\",
                "  --git-repo . --base origin/main --head HEAD \\",
                "  --coverage coverage.xml \\",
                "  --format sarif --output changeguard.sarif \\",
                "  --fail-on high",
              ].join("\n")}
            />
            <Plate label="exit codes" bodyClassName="divide-y divide-line text-[0.8125rem]">
              {[
                ["0", "No non-AI finding at or above the threshold."],
                ["1", "At least one deterministic or heuristic finding at or above it."],
                ["2", "Invalid input or a git error, such as a malformed patch or an unknown revision."],
              ].map(([code, text]) => (
                <div key={code} className="grid grid-cols-[36px_minmax(0,1fr)] gap-3 px-4 py-2.5">
                  <span className="font-mono font-semibold text-ink">{code}</span>
                  <span className="text-ink-soft">{text}</span>
                </div>
              ))}
            </Plate>
          </div>
          <div>
            <p className="text-[0.875rem] text-ink-soft">The recorded sample report in each format, as the engine wrote it:</p>
            <ul className="mt-3 flex flex-wrap gap-2">
              {[
                ["Markdown", sampleExports.markdown, "for a pull-request comment"],
                ["SARIF 2.1.0", sampleExports.sarif, "for code scanning"],
                ["JSON", sampleExports.json, "the full report, schema 1.0"],
              ].map(([label, href, hint]) => (
                <li key={label}>
                  <a
                    href={href}
                    download
                    className="inline-flex flex-col rounded-[10px] border border-line px-3.5 py-2.5 transition-colors hover:border-line-strong hover:bg-surface"
                  >
                    <span className="text-[0.8125rem] font-medium text-ink">{label} ↓</span>
                    <span className="text-[0.75rem] text-muted">{hint}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </Chapter>

        {/* ------------------------------------------------------------ Close */}
        <section className="border-t border-line py-16 sm:py-20">
          <h2 className="max-w-[22ch] text-[clamp(1.75rem,3.1vw,2.5rem)] font-[640] leading-[1.1] tracking-[-0.028em] [font-stretch:112%]">
            Now try a change of your own.
          </h2>
          <p className="prose-lab mt-4">
            Paste a diff, or upload a patch with a snapshot and a coverage report. Everything above runs the same way, and
            nothing leaves the machine the engine runs on unless you configure a hosted model.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/analyze" size="lg">
              Analyse a diff
            </ButtonLink>
            <ButtonLink href="/evaluation" size="lg" variant="secondary">
              How well does it work?
            </ButtonLink>
          </div>
        </section>
      </ExperienceShell>
    </>
  );
}
