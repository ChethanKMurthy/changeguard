"""Independent check that cited evidence is real.

For every finding the harness re-reads the case's own files and verifies that
each cited evidence item exists in the report, points at lines that exist in
the referenced revision, and that its excerpt matches those lines verbatim
(after the same secret masking the report applies). This is the
"unsupported evidence" metric: it should be exactly zero, and any regression
fails CI.
"""

from __future__ import annotations

from changeguard.analysis.secrets import redact
from changeguard.evaluation.dataset import Case
from changeguard.report.models import Evidence, EvidenceType, Finding, Report


def _lines(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def _evidence_ok(case: Case, e: Evidence) -> bool:
    if e.file is None or e.start_line is None:
        return True  # file-less evidence (e.g. a dependency summary) carries no location claim
    side = e.side or "head"
    text = case.read(side, e.file)
    if text is None:
        return False
    lines = _lines(text)
    end = e.end_line or e.start_line
    if not (1 <= e.start_line <= len(lines) and 1 <= end <= len(lines)):
        return False
    if e.excerpt is None:
        return True
    if e.type is EvidenceType.DIFF_HUNK and e.excerpt_start_line is None:
        # "-old\n+new" pairs: verify each side against its own revision.
        old_line, new_line = e.data.get("old_line"), e.data.get("new_line")
        base_text = case.read("base", e.file)
        for row in e.excerpt.split("\n"):
            if row.startswith("+") and isinstance(new_line, int):
                if redact(lines[new_line - 1]) != row[1:]:
                    return False
            elif row.startswith("-") and isinstance(old_line, int) and base_text is not None:
                base_lines = _lines(base_text)
                if old_line > len(base_lines) or redact(base_lines[old_line - 1]) != row[1:]:
                    return False
        return True
    start = e.excerpt_start_line or e.start_line
    for offset, row in enumerate(e.excerpt.split("\n")):
        number = start + offset
        if number > len(lines) or redact(lines[number - 1]) != row:
            return False
    return True


def unsupported_findings(case: Case, report: Report) -> list[str]:
    evidence = report.evidence_by_id()
    bad: list[str] = []
    for f in report.findings:
        if not _finding_ok(case, f, evidence):
            bad.append(f.id)
    return bad


def _finding_ok(case: Case, f: Finding, evidence: dict[str, Evidence]) -> bool:
    cited = list(f.evidence_ids)
    if f.ai_analysis is not None:
        cited += f.ai_analysis.evidence_ids
    if not f.evidence_ids:
        return False
    for eid in cited:
        e = evidence.get(eid)
        if e is None or not _evidence_ok(case, e):
            return False
    loc = f.location
    if loc.start_line is not None:
        text = case.read(loc.side, loc.file)
        if text is not None and loc.start_line > len(_lines(text)):
            return False
    return True
