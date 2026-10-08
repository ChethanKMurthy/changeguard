"""Command-line interface.

changeguard analyze change.patch --repo-archive repo.zip --coverage coverage.xml
changeguard analyze --git-repo . --base origin/main --head HEAD --format markdown
changeguard serve --port 8000
changeguard eval --dataset ../eval/dataset
changeguard samples
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

from changeguard import RULESET_VERSION, __version__
from changeguard.analysis.context import AnalysisOptions
from changeguard.analysis.pipeline import AnalysisPipeline
from changeguard.config import Settings, get_settings
from changeguard.errors import ChangeGuardError
from changeguard.ingest.prepare import prepare_input
from changeguard.report.models import SEVERITY_RANK, FindingKind, Report, Severity
from changeguard.storage.db import now

_COLORS = {
    "critical": "\033[1;31m",
    "high": "\033[31m",
    "medium": "\033[33m",
    "low": "\033[36m",
    "info": "\033[2m",
}
_RESET = "\033[0m"


def _git(repo: Path, *args: str) -> bytes:
    """Run git with repository-controlled execution hooks disabled."""
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
    argv = [
        "git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=",
        "-c", "core.pager=cat", "--no-pager", *args,
    ]  # fmt: skip
    proc = subprocess.run(argv, cwd=repo, env=env, capture_output=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise ChangeGuardError(
            f"git {' '.join(args[:2])} failed: {proc.stderr.decode(errors='replace').strip()[:300]}"
        )
    return proc.stdout


def _from_git(repo: Path, base: str, head: str | None) -> tuple[bytes, bytes]:
    diff_args = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "-M", base]
    if head:
        diff_args.append(head)
    patch = _git(repo, *diff_args)
    archive = _git(repo, "archive", "--format=tar", base)
    return patch, archive


def _synthesizer(settings: Settings, enabled: bool):  # type: ignore[no-untyped-def]
    if not enabled:
        return None
    from changeguard.ai.cache import MemoryCache
    from changeguard.ai.providers import build_provider
    from changeguard.ai.synthesizer import AISynthesizer

    provider = build_provider(settings)
    if provider is None:
        print(
            "warning: --ai requested but CHANGEGUARD_AI_PROVIDER=none; continuing without AI",
            file=sys.stderr,
        )
        return None
    return AISynthesizer(provider, cache=MemoryCache(), max_context_chars=settings.ai_max_context_chars,
                         max_findings=settings.ai_max_findings, temperature=settings.ai_temperature, seed=settings.ai_seed)  # fmt: skip


def run_analysis(
    settings: Settings,
    *,
    patch: bytes,
    archive: bytes | None,
    coverage: bytes | None,
    ai: bool,
    title: str | None = None,
    filenames: dict[str, str] | None = None,
) -> Report:
    prepared = prepare_input(
        settings, patch=patch, archive=archive, coverage=coverage, filenames=filenames
    )
    pipeline = AnalysisPipeline(
        synthesizer=_synthesizer(settings, ai), timeout_seconds=settings.analysis_timeout_seconds
    )
    return pipeline.run(
        prepared,
        analysis_id="cli_" + uuid.uuid4().hex[:12],
        created_at=now(),
        options=AnalysisOptions(ai_enabled=ai, title=title),
    )


def render_text(report: Report, *, color: bool) -> str:
    def paint(sev: str, text: str) -> str:
        return f"{_COLORS[sev]}{text}{_RESET}" if color else text

    s = report.summary
    lines = [
        f"ChangeGuard {report.engine_version} · ruleset {report.ruleset_version} · {report.input.mode.replace('_', ' ')}",
        f"{report.title}",
        f"{s.files_changed} files (+{s.additions} −{s.deletions}) · {s.findings_total} findings · review priority: "
        + paint(
            "high" if s.review_priority.level in ("block", "high") else "low",
            s.review_priority.level.upper(),
        ),
        "",
    ]
    for f in report.findings:
        loc = f.location.file + (f":{f.location.start_line}" if f.location.start_line else "")
        severity = f"{f.severity.value.upper():<8}"
        lines.append(
            f"  {paint(f.severity.value, severity)} {f.kind.value:<13} {f.rule_id:<14} {loc}"
        )
        lines.append(f"           {f.title}")
    if report.warnings:
        lines.append("")
        lines += [f"  ! {w}" for w in report.warnings]
    return "\n".join(lines)


def _exit_code(report: Report, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[Severity(fail_on)]
    gating = [
        f
        for f in report.findings
        if f.kind is not FindingKind.AI and SEVERITY_RANK[f.severity] >= threshold
    ]
    return 1 if gating else 0


def cmd_analyze(args: argparse.Namespace) -> int:
    settings = get_settings()
    archive: bytes | None = None
    if args.git_repo:
        patch, archive = _from_git(Path(args.git_repo), args.base, args.head)
    elif args.patch == "-":
        patch = sys.stdin.buffer.read()
    elif args.patch:
        patch = Path(args.patch).read_bytes()
    else:
        print(
            "error: provide a patch file, '-' for stdin, or --git-repo with --base", file=sys.stderr
        )
        return 2
    if args.repo_archive:
        archive = Path(args.repo_archive).read_bytes()
    coverage = Path(args.coverage).read_bytes() if args.coverage else None
    report = run_analysis(
        settings, patch=patch, archive=archive, coverage=coverage, ai=args.ai, title=args.title
    )

    from changeguard.report.exporters import to_json, to_markdown, to_sarif_json

    rendered = {
        "json": lambda: to_json(report),
        "markdown": lambda: to_markdown(report),
        "sarif": lambda: to_sarif_json(report),
        "text": lambda: render_text(report, color=sys.stdout.isatty() and not args.output),
    }[args.format]()
    if args.output:
        Path(args.output).write_text(rendered if rendered.endswith("\n") else rendered + "\n")
        print(f"wrote {args.output} ({report.summary.findings_total} findings)", file=sys.stderr)
    else:
        print(rendered)
    return _exit_code(report, args.fail_on)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "changeguard.api.app:create_default_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_samples(_: argparse.Namespace) -> int:
    from changeguard.samples import load_samples

    for sample in load_samples().values():
        print(f"{sample.id:<24} {sample.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="changeguard", description="Evidence-grounded code-change risk analysis."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"changeguard {__version__} (ruleset {RULESET_VERSION})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="analyse a patch")
    analyze.add_argument("patch", nargs="?", help="patch file, or '-' to read stdin")
    analyze.add_argument("--repo-archive", help="snapshot of the base revision (.zip/.tar.gz)")
    analyze.add_argument(
        "--git-repo", help="local git repository to diff (uses `git diff` and `git archive`)"
    )
    analyze.add_argument(
        "--base", default="HEAD", help="base revision for --git-repo (default: HEAD)"
    )
    analyze.add_argument("--head", help="head revision for --git-repo (default: working tree)")
    analyze.add_argument(
        "--coverage", help="coverage report (Cobertura XML, LCOV, coverage.py JSON)"
    )
    analyze.add_argument(
        "--ai", action="store_true", help="run AI synthesis with the configured provider"
    )
    analyze.add_argument("--title", help="report title")
    analyze.add_argument("--format", choices=["text", "json", "markdown", "sarif"], default="text")
    analyze.add_argument("--output", "-o", help="write the report to a file")
    analyze.add_argument(
        "--fail-on", choices=["critical", "high", "medium", "low", "never"], default="never",
        help="exit 1 if a non-AI finding at or above this severity exists (CI gate)",
    )  # fmt: skip
    analyze.set_defaults(func=cmd_analyze)

    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    samples = sub.add_parser("samples", help="list built-in sample scenarios")
    samples.set_defaults(func=cmd_samples)

    from changeguard.evaluation.cli import add_eval_parser

    add_eval_parser(sub)

    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except ChangeGuardError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
