"""Shared state for one analysis run: workspace, evidence store, and findings."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from changeguard.analysis.rules.catalog import RULES, Rule
from changeguard.analysis.secrets import redact
from changeguard.analysis.workspace import ChangedFile, Workspace
from changeguard.ingest.coverage import CoverageReport
from changeguard.ingest.diff_parser import PatchSet
from changeguard.report.models import (
    Category,
    Confidence,
    Evidence,
    EvidenceType,
    Explanation,
    Finding,
    FindingKind,
    Location,
    Severity,
    Side,
    SuggestedTest,
)

MAX_EXCERPT_LINES = 30


@dataclass(slots=True)
class AnalysisOptions:
    ai_enabled: bool = False
    title: str | None = None
    # Stages to skip, for evaluation ablations only (e.g. {"tests"}).
    disabled_stages: frozenset[str] = frozenset()


class EvidenceStore:
    """Append-only evidence registry with de-duplication and redaction.

    Evidence IDs are assigned sequentially (E1, E2, ...) in pipeline order,
    which is deterministic for a given input.
    """

    def __init__(self) -> None:
        self._items: list[Evidence] = []
        self._index: dict[tuple[Any, ...], str] = {}

    def add(
        self,
        type: EvidenceType,
        title: str,
        *,
        source: str,
        file: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        side: Side | None = None,
        excerpt: str | None = None,
        excerpt_start_line: int | None = None,
        highlight_lines: Iterable[int] = (),
        data: dict[str, Any] | None = None,
    ) -> str:
        key = (type, title, file, start_line, end_line, side, excerpt)
        existing = self._index.get(key)
        if existing is not None:
            return existing
        evidence_id = f"E{len(self._items) + 1}"
        self._items.append(
            Evidence(
                id=evidence_id,
                type=type,
                title=redact(title),
                file=file,
                start_line=start_line,
                end_line=end_line if end_line is not None else start_line,
                side=side,
                excerpt=redact(excerpt) if excerpt is not None else None,
                excerpt_start_line=excerpt_start_line,
                highlight_lines=sorted(set(highlight_lines)),
                source=source,
                data=data or {},
            )
        )
        self._index[key] = evidence_id
        return evidence_id

    def get(self, evidence_id: str) -> Evidence | None:
        for e in self._items:
            if e.id == evidence_id:
                return e
        return None

    def all(self) -> list[Evidence]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


@dataclass(slots=True)
class AnalysisContext:
    patch: PatchSet
    workspace: Workspace
    coverage: CoverageReport | None
    options: AnalysisOptions
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Populated by stages; typed loosely to avoid import cycles.
    symbol_changes: list[Any] = field(default_factory=list)
    repo_index: Any = None
    coverage_matches: dict[str, Any] = field(default_factory=dict)
    stage_data: dict[str, Any] = field(default_factory=dict)

    @property
    def files(self) -> list[ChangedFile]:
        return self.workspace.files

    @property
    def full_context(self) -> bool:
        return self.workspace.mode == "full_context"

    # -- source access --------------------------------------------------------

    def source(self, path: str, side: Side = "head") -> str | None:
        cf = self.workspace.file(path)
        if cf is not None:
            text = cf.head_text if side == "head" else cf.base_text
            if text is not None:
                return text
        repo = self.workspace.head_repo if side == "head" else self.workspace.base_repo
        return repo.get(path)

    def excerpt(
        self,
        path: str,
        start: int,
        end: int | None = None,
        *,
        side: Side = "head",
        context: int = 2,
    ) -> tuple[str, int] | None:
        """Verbatim lines ``[start-context, end+context]`` from the requested revision.

        Falls back to the diff hunks when the full file is unavailable. Returns
        ``(text, first_line_number)`` or ``None`` when nothing is visible.
        """
        end = end if end is not None else start
        text = self.source(path, side)
        if text is not None:
            lines = text.split("\n")
            if text.endswith("\n"):
                lines = lines[:-1]
            if not lines or start > len(lines):
                return None
            lo = max(1, start - context)
            hi = min(len(lines), end + context, lo + MAX_EXCERPT_LINES - 1)
            return "\n".join(lines[lo - 1 : hi]), lo
        cf = self.workspace.file(path)
        if cf is None:
            return None
        visible: dict[int, str] = {}
        for hunk in cf.diff.hunks:
            for ln in hunk.lines:
                number = ln.new_lineno if side == "head" else ln.old_lineno
                if number is not None and (
                    ln.kind == "context" or (ln.kind == "add") == (side == "head")
                ):
                    visible[number] = ln.content
        wanted = [n for n in range(max(1, start - context), end + context + 1) if n in visible]
        if not wanted:
            return None
        # Keep the contiguous block that contains `start`.
        block = [n for n in wanted if n >= start - context]
        contiguous: list[int] = []
        for n in block:
            if contiguous and n != contiguous[-1] + 1:
                break
            contiguous.append(n)
        contiguous = contiguous[:MAX_EXCERPT_LINES]
        return "\n".join(visible[n] for n in contiguous), contiguous[0]

    def code_evidence(
        self,
        path: str,
        start: int,
        end: int | None = None,
        *,
        side: Side = "head",
        title: str | None = None,
        type: EvidenceType = EvidenceType.CODE,
        source: str | None = None,
        data: dict[str, Any] | None = None,
        context: int = 2,
        highlight: Iterable[int] | None = None,
    ) -> str | None:
        end = end if end is not None else start
        snippet = self.excerpt(path, start, end, side=side, context=context)
        if snippet is None:
            return None
        text, first = snippet
        return self.evidence.add(
            type,
            title or (f"{path}:{start}" if start == end else f"{path}:{start}-{end}"),
            source=source or ("repository snapshot" if self.full_context else "diff"),
            file=path,
            start_line=start,
            end_line=end,
            side=side,
            excerpt=text,
            excerpt_start_line=first,
            highlight_lines=highlight if highlight is not None else range(start, end + 1),
            data=data,
        )

    # -- findings -------------------------------------------------------------

    def add_finding(
        self,
        rule_id: str,
        *,
        title: str,
        description: str,
        location: Location,
        evidence_ids: Iterable[str | None],
        failure_scenario: str,
        suggested_test: SuggestedTest,
        severity: Severity | None = None,
        confidence: Confidence = Confidence.HIGH,
        kind: FindingKind | None = None,
        category: Category | None = None,
        explanation: str | None = None,
        related_symbols: Iterable[str] = (),
        tags: Iterable[str] = (),
        discriminator: str = "",
        rule: Rule | None = None,
    ) -> Finding:
        meta = rule or RULES[rule_id]
        ids = [e for e in evidence_ids if e]
        if not ids:
            raise ValueError(f"finding {rule_id} has no evidence; every finding must cite evidence")
        digest = hashlib.sha1(
            f"{rule_id}|{location.file}|{location.start_line}|{discriminator}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:10]
        finding = Finding(
            id=f"F-{digest}",
            rule_id=rule_id,
            category=category or meta.category,
            kind=kind or meta.kind,
            title=redact(title),
            description=redact(description),
            severity=severity or meta.severity,
            confidence=confidence,
            location=location,
            evidence_ids=list(dict.fromkeys(ids)),
            failure_scenario=failure_scenario,
            suggested_test=suggested_test,
            explanation=Explanation(text=explanation or meta.rationale, source="template"),
            related_symbols=list(dict.fromkeys(related_symbols)),
            tags=list(dict.fromkeys(tags)),
        )
        if any(f.id == finding.id for f in self.findings):
            return next(f for f in self.findings if f.id == finding.id)
        self.findings.append(finding)
        return finding
