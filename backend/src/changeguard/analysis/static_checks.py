"""Differential static analysis.

Python files are checked with Ruff (a curated, risk-relevant rule set) on both
revisions; a diagnostic is reported only if it is *new* in the head revision.
Diagnostics are matched across revisions by (rule code, normalised source
line), so moved code does not produce false "new" diagnostics, and pre-existing
issues are never blamed on the change.

Safety: Ruff reads the source from stdin and never executes it. It is run with
``--isolated`` so configuration files inside the uploaded repository are
ignored, with a timeout and a minimal environment.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.rules.catalog import RUFF_RULES, RUFF_SELECT, RULES, Rule, ruff_rule_id
from changeguard.analysis.workspace import ChangedFile
from changeguard.languages.model import LanguageId
from changeguard.report.models import (
    Category,
    Confidence,
    EvidenceType,
    FindingKind,
    Location,
    Severity,
    SuggestedTest,
)

_MEDIUM_CONFIDENCE = frozenset(
    {
        "S608",
        "S105",
        "S106",
        "S107",
        "S311",
        "S324",
        "S113",
        "S104",
        "S103",
        "S202",
        "BLE001",
        "B008",
        "B018",
        "T201",
    }
)
_SAFE_ALTERNATIVES = {
    "S307": "use `ast.literal_eval` for literals or an explicit parser",
    "S102": "remove `exec`; dispatch to explicit functions instead",
    "S301": "deserialise with `json` or a schema-validated format",
    "S506": "use `yaml.safe_load`",
    "S602": "pass an argument list without `shell=True`",
    "S604": "pass an argument list without `shell=True`",
    "S605": "use `subprocess.run([...])` without a shell",
    "S608": "use parameterised queries (placeholders) instead of string formatting",
    "S501": "keep certificate verification enabled (`verify=True`, or a CA bundle path)",
    "S323": "use `ssl.create_default_context()`",
    "S324": "use `hashlib.sha256` (or a password hash such as argon2/bcrypt for credentials)",
    "S701": "enable autoescape (`select_autoescape()`)",
    "S201": "never enable debug mode outside local development",
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    line: int
    end_line: int
    url: str | None


@functools.cache
def ruff_binary() -> str | None:
    try:
        from ruff.__main__ import find_ruff_bin

        path = str(find_ruff_bin())
        return path if os.path.exists(path) else None
    except (ImportError, FileNotFoundError):
        return shutil.which("ruff")


@functools.cache
def ruff_version() -> str | None:
    binary = ruff_binary()
    if binary is None:
        return None
    try:
        out = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def run_ruff(source: str, filename: str, timeout: float = 15.0) -> list[Diagnostic] | None:
    """Run Ruff on ``source`` via stdin. Returns ``None`` if Ruff is unavailable or failed."""
    binary = ruff_binary()
    if binary is None:
        return None
    argv = [
        binary, "check", "--isolated", "--no-cache", "--output-format", "json",
        "--select", RUFF_SELECT, "--stdin-filename", os.path.basename(filename) or "module.py", "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(
            argv,
            input=source,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=tempfile.gettempdir(),
            env={"PATH": os.environ.get("PATH", ""), "NO_COLOR": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in (0, 1):
        return None
    try:
        raw = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    out: list[Diagnostic] = []
    for item in raw:
        code = item.get("code") or "invalid-syntax"
        loc = item.get("location") or {}
        end = item.get("end_location") or loc
        out.append(
            Diagnostic(
                code=str(code),
                message=str(item.get("message", "")),
                line=int(loc.get("row", 1)),
                end_line=int(end.get("row", loc.get("row", 1))),
                url=item.get("url"),
            )
        )
    return out


def _line(text: str, number: int) -> str:
    lines = text.split("\n")
    return " ".join(lines[number - 1].split()) if 0 < number <= len(lines) else ""


def analyze_static(ctx: AnalysisContext) -> dict[str, object]:
    python_files = [
        cf for cf in ctx.files
        if cf.language is LanguageId.PYTHON and cf.head_text is not None and cf.full_context and not cf.diff.is_binary
    ]  # fmt: skip
    stats: dict[str, object] = {
        "python_files": len(python_files),
        "new_diagnostics": 0,
        "tool": ruff_version(),
    }
    if python_files and ruff_binary() is None:
        ctx.warnings.append("Ruff is not available; Python static checks were skipped.")
        stats["skipped"] = "ruff unavailable"
    elif python_files:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_ruff_pair, python_files))
        for cf, (head_diags, base_diags) in zip(python_files, results, strict=True):
            if head_diags is None:
                ctx.warnings.append(
                    f"Ruff failed on {cf.path}; static checks skipped for that file."
                )
                continue
            new = _new_diagnostics(cf, head_diags, base_diags or [])
            stats["new_diagnostics"] = int(str(stats["new_diagnostics"])) + len(new)
            _report_python(ctx, cf, new)
    stats["syntax_errors"] = _syntax_errors_js(ctx)
    return stats


def _ruff_pair(cf: ChangedFile) -> tuple[list[Diagnostic] | None, list[Diagnostic] | None]:
    assert cf.head_text is not None
    head = run_ruff(cf.head_text, cf.path)
    base = run_ruff(cf.base_text, cf.old_path or cf.path) if cf.base_text is not None else []
    return head, base


def _new_diagnostics(
    cf: ChangedFile, head: list[Diagnostic], base: list[Diagnostic]
) -> list[Diagnostic]:
    assert cf.head_text is not None
    base_keys: Counter[tuple[str, str]] = Counter(
        (d.code, _line(cf.base_text or "", d.line)) for d in base
    )
    new: list[Diagnostic] = []
    for d in head:
        key = (d.code, _line(cf.head_text, d.line))
        if base_keys[key] > 0:
            base_keys[key] -= 1
            continue
        new.append(d)
    return new


def _report_python(ctx: AnalysisContext, cf: ChangedFile, diags: list[Diagnostic]) -> None:
    syntax = [d for d in diags if d.code == "invalid-syntax"]
    if syntax:
        first = syntax[0]
        ev = ctx.code_evidence(
            cf.path, first.line, first.end_line, title=f"Syntax error at {cf.path}:{first.line}",
            type=EvidenceType.STATIC_DIAGNOSTIC, source=f"ruff ({ruff_version() or 'unknown version'})",
            data={"code": "invalid-syntax", "messages": [f"line {d.line}: {d.message}" for d in syntax[:10]]},
        )  # fmt: skip
        ctx.add_finding(
            "CG-SYN-001",
            title=f"Syntax error introduced in {cf.path}",
            description=f"{cf.path} no longer parses: {first.message} (line {first.line}).",
            location=Location(file=cf.path, start_line=first.line, end_line=first.end_line),
            evidence_ids=[ev],
            failure_scenario=f"Importing {cf.path} raises SyntaxError, so every module that imports it fails to load.",
            suggested_test=SuggestedTest(
                description="Fix the syntax error; `python -m compileall` or an import smoke test in CI catches this.",
                kind="static",
                code=f"python -m py_compile {cf.path}",
                language="shell",
            ),
        )
    for d in diags:
        if d.code == "invalid-syntax" or d.code not in RUFF_RULES:
            continue
        category, severity, rationale = RUFF_RULES[d.code]
        is_test = cf.is_test
        if is_test and category in (Category.DEBUG_ARTIFACT, Category.SECRET_EXPOSURE):
            continue  # prints and fake credentials are normal in tests
        rule = Rule(
            ruff_rule_id(d.code),
            f"Ruff {d.code}",
            category,
            FindingKind.DETERMINISTIC,
            severity,
            rationale,
            ("python",),
        )
        changed_line = any(ln in cf.added for ln in range(d.line, d.end_line + 1))
        ev = ctx.code_evidence(
            cf.path, d.line, d.end_line, title=f"Ruff {d.code} at {cf.path}:{d.line}",
            type=EvidenceType.STATIC_DIAGNOSTIC, source=f"ruff ({ruff_version() or 'unknown version'})",
            data={"code": d.code, "message": d.message, "url": d.url, "on_changed_line": changed_line},
        )  # fmt: skip
        symbol = cf.head_index.innermost_symbol(d.line) if cf.head_index else None
        where = f" in `{symbol.qualname}`" if symbol else ""
        description = (
            f"{d.message} (Ruff {d.code}){where}. This diagnostic is new in the head revision."
        )
        if not changed_line:
            description += (
                " The flagged line itself is unchanged; another part of this change (for example a removed import "
                "or definition) introduced it."
            )
        ctx.add_finding(
            rule.id,
            rule=rule,
            title=d.message if len(d.message) < 110 else d.message[:107] + "…",
            description=description,
            location=Location(
                file=cf.path,
                start_line=d.line,
                end_line=d.end_line,
                symbol=symbol.qualname if symbol else None,
            ),
            evidence_ids=[ev],
            failure_scenario=_failure_for(d, symbol.qualname if symbol else None),
            suggested_test=_test_for(d, category, cf, symbol.qualname if symbol else None),
            severity=Severity.LOW
            if is_test
            and severity in (Severity.MEDIUM, Severity.HIGH)
            and category is not Category.CORRECTNESS
            else severity,
            confidence=Confidence.MEDIUM if d.code in _MEDIUM_CONFIDENCE else Confidence.HIGH,
            related_symbols=[symbol.qualname] if symbol else [],
            tags=["ruff", d.code],
            discriminator=d.code + d.message,
        )


def _failure_for(d: Diagnostic, symbol: str | None) -> str:
    where = f"`{symbol}`" if symbol else f"line {d.line}"
    code = d.code
    if code == "F821":
        return f"When {where} runs, line {d.line} raises NameError."
    if code == "F823":
        return f"When {where} runs, line {d.line} raises UnboundLocalError."
    if code.startswith("S") and code in _SAFE_ALTERNATIVES:
        return f"Attacker-influenced input reaching line {d.line} is interpreted unsafely ({d.message.rstrip('.')})."
    if code.startswith("ASYNC") or code == "RUF006":
        return f"Under load, {where} blocks the event loop and stalls every concurrent request."
    if code in ("E722", "S110", "BLE001", "B012"):
        return f"A failure inside {where} is swallowed; the caller proceeds with missing or partial results."
    if code.startswith("T"):
        return f"{where} emits debug output or pauses in production."
    return f"When line {d.line} executes: {RUFF_RULES[code][2]}"


def _test_for(
    d: Diagnostic, category: Category, cf: ChangedFile, symbol: str | None
) -> SuggestedTest:
    target = f"`{symbol}`" if symbol else f"line {d.line}"
    if category is Category.SECURITY:
        alt = _SAFE_ALTERNATIVES.get(d.code)
        return SuggestedTest(
            description=f"Add a negative test that feeds hostile input to {target} and asserts it is rejected"
            + (f"; {alt}." if alt else "."),
            kind="unit",
        )
    if category is Category.ERROR_HANDLING:
        return SuggestedTest(
            description=f"Add a test that makes the guarded call in {target} raise, and assert the error is "
            "surfaced (logged or re-raised) rather than swallowed.",
            kind="unit",
        )
    if category is Category.CONCURRENCY:
        return SuggestedTest(
            description=f"Exercise {target} under asyncio debug mode (PYTHONASYNCIODEBUG=1) and assert no slow-callback "
            "warnings; switch to the async equivalent of the blocking call.",
            kind="integration",
        )
    if category is Category.DEBUG_ARTIFACT:
        return SuggestedTest(
            description="Remove the debug statement; enable Ruff T10/T20 in CI.", kind="static"
        )
    return SuggestedTest(
        description=f"Add a unit test that executes {target} (line {d.line}); it fails immediately while this "
        "diagnostic is present.",
        kind="unit",
    )


def _syntax_errors_js(ctx: AnalysisContext) -> int:
    """Tree-sitter syntax errors for JS/TS files (Python syntax is reported via Ruff)."""
    count = 0
    rule: Rule = RULES["CG-SYN-001"]
    for cf in ctx.files:
        if cf.language in (None, LanguageId.PYTHON) or not cf.full_context or cf.head_index is None:
            continue
        head_errors = cf.head_index.parse_error_lines
        base_errors = cf.base_index.parse_error_lines if cf.base_index else []
        if len(head_errors) <= len(base_errors):
            continue
        new_lines = [ln for ln in head_errors if ln in cf.added] or head_errors[len(base_errors) :]
        first = new_lines[0]
        ev = ctx.code_evidence(
            cf.path, first, first, title=f"Parse error at {cf.path}:{first}", type=EvidenceType.STATIC_DIAGNOSTIC,
            source="tree-sitter", data={"error_lines": new_lines[:10]},
        )  # fmt: skip
        ctx.add_finding(
            rule.id,
            title=f"Syntax error introduced in {cf.path}",
            description=f"{cf.path} has {len(head_errors)} parse error(s) after the change (line {first} first).",
            location=Location(file=cf.path, start_line=first, end_line=first),
            evidence_ids=[ev],
            failure_scenario=f"The bundler/compiler rejects {cf.path}; the build fails or the module fails to load.",
            suggested_test=SuggestedTest(
                description="Fix the syntax error; run the compiler/linter (e.g. `tsc --noEmit`, `eslint`) in CI.",
                kind="static",
            ),
        )
        count += 1
    return count
