"""Condition-logic change heuristic.

Pairs each removed line with its most similar added line and diffs them at
token level. If the only differences are comparison/boolean operators,
negation, or numeric constants in a condition, the change shifts a boundary or
inverts a condition. That is a behaviour change worth a boundary-value test,
whether or not it is a bug, so the rule is labelled *heuristic*.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.workspace import ChangedFile
from changeguard.ingest.diff_parser import Hunk
from changeguard.report.models import Confidence, EvidenceType, Location, Severity, SuggestedTest

_TOKEN = re.compile(
    r"""
    "(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`   # strings
    |\b\d+(?:\.\d+)?\b                                      # numbers
    |===|!==|==|!=|<=|>=|&&|\|\||\?\?|<<|>>|[<>!+\-*/%]     # operators
    |[A-Za-z_$][\w$]*                                       # words
    |[()\[\]{}.,:;?=]                                       # punctuation
    """,
    re.VERBOSE,
)
COMPARISON = frozenset({"<", "<=", ">", ">=", "==", "!=", "===", "!==", "is", "in"})
BOOLEAN = frozenset({"and", "or", "&&", "||", "??"})
NEGATION = frozenset({"not", "!"})
BOOLEAN_LITERALS = frozenset({"True", "False", "true", "false"})
_CONDITION = re.compile(
    r"^\s*(if|elif|while|return|assert|else\s+if|case)\b|\?|\b(and|or)\b|&&|\|\||[<>]=?|==|!=|\brange\(|\[.*:.*\]"
)
_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--")
# Definition lines: parameter defaults are handled by the signature rules (CG-API-005).
_DEFINITION = re.compile(
    r"^\s*(?:async\s+)?def\s|^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function[\s*]|^\s*class\s"
)
# Arrows are not comparisons.
_ARROWS = re.compile(r"->|=>")


@dataclass(slots=True)
class LogicChange:
    old_line: int
    new_line: int
    old_text: str
    new_text: str
    rule_id: str
    summary: str
    severity: Severity


def _tokens(line: str) -> list[str]:
    return _TOKEN.findall(line)


def analyze_logic(ctx: AnalysisContext) -> dict[str, int]:
    count = 0
    for cf in ctx.files:
        if cf.language is None or cf.is_test or cf.diff.is_binary:
            continue
        for hunk in cf.diff.hunks:
            for change in _hunk_changes(hunk):
                _report(ctx, cf, change)
                count += 1
    return {"logic_changes": count}


def _hunk_changes(hunk: Hunk) -> list[LogicChange]:
    out: list[LogicChange] = []
    lines = hunk.lines
    i = 0
    while i < len(lines):
        if lines[i].kind != "del":
            i += 1
            continue
        dels = []
        while i < len(lines) and lines[i].kind == "del":
            dels.append(lines[i])
            i += 1
        adds = []
        while i < len(lines) and lines[i].kind == "add":
            adds.append(lines[i])
            i += 1
        used: set[int] = set()
        for d in dels:
            best: tuple[float, int] | None = None
            for j, a in enumerate(adds):
                if j in used:
                    continue
                ratio = difflib.SequenceMatcher(None, d.content.strip(), a.content.strip()).ratio()
                if ratio >= 0.6 and (best is None or ratio > best[0]):
                    best = (ratio, j)
            if best is None:
                continue
            used.add(best[1])
            a = adds[best[1]]
            assert d.old_lineno is not None and a.new_lineno is not None
            classified = _classify(d.content, a.content)
            if classified is not None:
                rule_id, summary, severity = classified
                out.append(
                    LogicChange(
                        d.old_lineno, a.new_lineno, d.content, a.content, rule_id, summary, severity
                    )
                )
    return out


def _classify(old: str, new: str) -> tuple[str, str, Severity] | None:
    if old.strip().startswith(_COMMENT_PREFIXES) or new.strip().startswith(_COMMENT_PREFIXES):
        return None
    if _DEFINITION.search(old) or _DEFINITION.search(new):
        return None
    old_cond, new_cond = _ARROWS.sub(" ", old), _ARROWS.sub(" ", new)
    if not (_CONDITION.search(old_cond) or _CONDITION.search(new_cond)):
        return None
    a, b = _tokens(old), _tokens(new)
    if a == b:
        return None
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    diffs = [
        (tag, a[i1:i2], b[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"
    ]
    if not diffs or sum(len(x) + len(y) for _, x, y in diffs) > 6:
        return None
    changed = [t for _, x, y in diffs for t in (*x, *y)]
    descriptions: list[str] = []
    for tag, x, y in diffs:
        old_s, new_s = " ".join(x), " ".join(y)
        if tag == "replace":
            descriptions.append(f"`{old_s}` → `{new_s}`")
        elif tag == "insert":
            descriptions.append(f"`{new_s}` added")
        else:
            descriptions.append(f"`{old_s}` removed")
    summary = ", ".join(descriptions)
    logical = COMPARISON | BOOLEAN | NEGATION | BOOLEAN_LITERALS
    if all(t in logical for t in changed):
        return "CG-LOG-001", summary, Severity.MEDIUM
    numeric_or_step = all(t.replace(".", "", 1).isdigit() or t in ("+", "-") for t in changed)
    if numeric_or_step and any(t.replace(".", "", 1).isdigit() for t in changed):
        off_by_one = any(t in ("+", "-") for t in changed) and "1" in changed
        return "CG-LOG-002", summary, Severity.MEDIUM if off_by_one else Severity.LOW
    return None


def _report(ctx: AnalysisContext, cf: ChangedFile, change: LogicChange) -> None:
    ev = ctx.evidence.add(
        EvidenceType.DIFF_HUNK,
        f"Condition changed at {cf.path}:{change.new_line}",
        source="diff",
        file=cf.path,
        start_line=change.new_line,
        end_line=change.new_line,
        side="head",
        excerpt=f"-{change.old_text}\n+{change.new_text}",
        highlight_lines=[change.new_line],
        data={"old_line": change.old_line, "new_line": change.new_line, "change": change.summary},
    )
    symbol = cf.head_index.innermost_symbol(change.new_line) if cf.head_index else None
    where = f" in `{symbol.qualname}`" if symbol else ""
    is_boundary = change.rule_id == "CG-LOG-002"
    ctx.add_finding(
        change.rule_id,
        title=("Boundary constant changed" if is_boundary else "Condition logic changed")
        + f": {change.summary}",
        description=f"Line {change.new_line}{where} changed only in {change.summary}; the condition's boundary or "
        "polarity is different now.",
        location=Location(
            file=cf.path,
            start_line=change.new_line,
            end_line=change.new_line,
            symbol=symbol.qualname if symbol else None,
        ),
        evidence_ids=[ev],
        failure_scenario="Inputs exactly at the boundary (or on the side the condition now excludes/includes) take "
        "the other branch than before — the classic off-by-one / inverted-condition regression.",
        suggested_test=SuggestedTest(
            description="Add boundary-value tests: the threshold itself, one below, and one above, asserting the "
            "intended branch for each.",
            kind="unit",
        ),
        severity=change.severity,
        confidence=Confidence.MEDIUM,
        related_symbols=[symbol.qualname] if symbol else [],
        tags=["boundary"],
        discriminator=change.summary,
    )
