"""Grounding verification of model output.

Every claim the model makes is checked against the context pack *before* it
can reach the report. A claim is rejected (never repaired) when it

* cites no evidence, or cites evidence IDs that were not in the pack;
* targets a finding ID that does not exist;
* mentions a file path that is not part of the change or its evidence;
* mentions line numbers outside the ranges of the evidence it cites;
* states a percentage that appears nowhere in the evidence (fabricated
  coverage/metric numbers);
* asserts test or CI outcomes as facts (the system runs no tests);
* is empty or degenerate.

Rejected claims are kept in the report's verification section with their
reasons, so the filtering itself is auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from changeguard.ai.context import ContextPack
from changeguard.ai.schemas import AdditionalRisk, FindingNote
from changeguard.report.models import Evidence

LINE_TOLERANCE = 3
_PATH = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|pyi|js|jsx|mjs|cjs|ts|tsx|mts|cts|sql|json|toml|ya?ml|txt|cfg|ini|go|rs|java|rb|php|cs|sh))(?![\w/])"
)
_LINE_REF = re.compile(
    r"(?i)\blines?\s+(\d{1,6})(?:\s*(?:-|–|to|through)\s*(\d{1,6}))?|(?<=[\w)]):(\d{1,6})\b"
)
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_TEST_RESULT = re.compile(
    r"(?i)\b(tests?|test suite|suite|ci|build|pipeline)\b[^.\n]{0,40}?\b(passed|failed|is failing|are failing|is passing|are passing|currently fail\w*|currently pass\w*|went red|is red|is green)\b"
)
_MIN_TEXT = 12
# Code identifiers the model names: `backticked` names, or snake_case/camelCase
# words next to "function"/"method"/"class".
_BACKTICK_SYMBOL = re.compile(r"`([A-Za-z_][\w.]*)(?:\(\))?`")
_NAMED_SYMBOL = re.compile(
    r"\b(?:function|method|class|helper)\s+`?([A-Za-z_]\w*(?:_\w+|[a-z][A-Z]\w*))`?|\b`?([A-Za-z_]\w*(?:_\w+|[a-z][A-Z]\w*))`?\s+(?:function|method|class|helper)\b"
)
_KEYWORDS = frozenset(
    {
        "None",
        "True",
        "False",
        "null",
        "undefined",
        "self",
        "this",
        "await",
        "async",
        "return",
        "try",
        "except",
        "catch",
        "if",
        "else",
        "elif",
    }
)


@dataclass(slots=True)
class Verdict:
    accepted: bool
    reasons: list[str] = field(default_factory=list)


class GroundingVerifier:
    def __init__(self, pack: ContextPack, finding_ids: set[str]) -> None:
        self.pack = pack
        self.finding_ids = finding_ids
        self.evidence: dict[str, Evidence] = {e.id: e for e in pack.evidence}
        self.known_files = {p for p in pack.known_files if p}
        self.known_basenames = {PurePosixPath(p).name for p in self.known_files}
        corpus = " ".join([pack.change_summary, pack.findings_text, pack.evidence_text])
        self.known_percentages = {m.group(1) for m in _PERCENT.finditer(corpus)}

    # -- public API -------------------------------------------------------------

    def check_note(self, note: FindingNote, finding_text: str = "") -> Verdict:
        reasons: list[str] = []
        if note.finding_id not in self.finding_ids:
            reasons.append(f"unknown_finding: '{note.finding_id}' is not a finding in this report")
        reasons += self._check_common(
            note.evidence_ids,
            [
                note.explanation,
                note.failure_scenario,
                note.suggested_test.description,
                note.uncertainty,
            ],
            code=note.suggested_test.code,
            extra_corpus=finding_text,
        )
        if len(note.explanation.strip()) < _MIN_TEXT:
            reasons.append("empty_text: explanation is empty or too short")
        return Verdict(not reasons, reasons)

    def check_risk(self, risk: AdditionalRisk) -> Verdict:
        reasons = self._check_common(
            risk.evidence_ids,
            [
                risk.title,
                risk.description,
                risk.failure_scenario,
                risk.suggested_test.description,
                risk.uncertainty,
            ],
            code=risk.suggested_test.code,
        )
        cited = [self.evidence[e] for e in risk.evidence_ids if e in self.evidence]
        if cited and not any(e.file and e.start_line for e in cited):
            reasons.append("no_location: cited evidence has no file location to anchor the risk")
        if len(risk.description.strip()) < _MIN_TEXT or len(risk.title.strip()) < 4:
            reasons.append("empty_text: title or description is empty or too short")
        return Verdict(not reasons, reasons)

    def check_text(self, text: str) -> Verdict:
        """Free text (overall assessment): paths, percentages and test-result claims only."""
        reasons = self._paths(text) + self._percentages(text) + self._test_results(text)
        return Verdict(not reasons, reasons)

    # -- checks ---------------------------------------------------------------------

    def _check_common(
        self, evidence_ids: list[str], texts: list[str], *, code: str, extra_corpus: str = ""
    ) -> list[str]:
        reasons: list[str] = []
        if not evidence_ids:
            reasons.append("no_evidence: the claim cites no evidence")
        unknown = [e for e in evidence_ids if e not in self.evidence]
        if unknown:
            reasons.append(
                f"unknown_evidence: cites {', '.join(unknown[:4])} which were not provided"
            )
        prose = "\n".join(texts)
        reasons += self._paths(prose)
        reasons += self._lines(
            prose, [self.evidence[e] for e in evidence_ids if e in self.evidence]
        )
        reasons += self._percentages(prose)
        reasons += self._test_results(prose)
        reasons += self._symbols(
            prose, [self.evidence[e] for e in evidence_ids if e in self.evidence], extra_corpus
        )
        # Code may reference module paths in imports; only file paths are checked there.
        reasons += self._paths(code)
        return reasons

    def _symbols(self, text: str, cited: list[Evidence], extra_corpus: str) -> list[str]:
        """Named code identifiers must occur in the evidence the claim cites (catches misattribution)."""
        corpus_parts = [extra_corpus]
        for e in cited:
            corpus_parts += [e.title, e.excerpt or "", str(e.data)]
        corpus = "\n".join(corpus_parts)
        names: list[str] = [m.group(1) for m in _BACKTICK_SYMBOL.finditer(text)]
        names += [m.group(1) or m.group(2) for m in _NAMED_SYMBOL.finditer(text)]
        bad: list[str] = []
        for name in names:
            if not name or name in _KEYWORDS or len(name) < 3:
                continue
            leaf = name.rsplit(".", 1)[-1]
            if re.search(rf"\b{re.escape(leaf)}\b", corpus):
                continue
            bad.append(name)
        return [
            f"symbol_not_in_evidence: names `{b}`, which does not appear in the cited evidence"
            for b in dict.fromkeys(bad)
        ]

    def _paths(self, text: str) -> list[str]:
        bad: list[str] = []
        for m in _PATH.finditer(text):
            path = m.group(1)
            if path in self.known_files or PurePosixPath(path).name in self.known_basenames:
                continue
            if (
                "/" not in path
                and path.count(".") == 1
                and path.split(".")[0] in {"e", "i", "etc", "vs"}
            ):
                continue
            bad.append(path)
        return [
            f"unknown_path: mentions '{p}', which is not part of this change"
            for p in dict.fromkeys(bad)
        ]

    def _lines(self, text: str, cited: list[Evidence]) -> list[str]:
        ranges = [
            (
                (e.excerpt_start_line or e.start_line or 0),
                max(e.end_line or 0, (e.excerpt_start_line or 0) + (e.excerpt or "").count("\n")),
            )
            for e in cited
            if e.start_line is not None
        ]
        bad: list[str] = []
        for m in _LINE_REF.finditer(text):
            start = int(m.group(1) or m.group(3))
            end = int(m.group(2)) if m.group(2) else start
            if not ranges or not any(
                lo - LINE_TOLERANCE <= start and end <= hi + LINE_TOLERANCE for lo, hi in ranges
            ):
                bad.append(f"{start}" if start == end else f"{start}-{end}")
        return [
            f"line_out_of_range: mentions line {b}, outside the cited evidence"
            for b in dict.fromkeys(bad)
        ]

    def _percentages(self, text: str) -> list[str]:
        bad = [
            m.group(1) for m in _PERCENT.finditer(text) if m.group(1) not in self.known_percentages
        ]
        return [
            f"unsupported_number: states {b}% which appears nowhere in the evidence"
            for b in dict.fromkeys(bad)
        ]

    def _test_results(self, text: str) -> list[str]:
        m = _TEST_RESULT.search(text)
        if m is None:
            return []
        window = text[max(0, m.start() - 25) : m.end()].lower()
        if any(
            word in window
            for word in (
                "would",
                "will",
                "could",
                "may ",
                "might",
                "should",
                "if ",
                "when",
                "unless",
            )
        ):
            return []
        return [f"claims_test_result: asserts '{m.group(0)[:60]}', but no tests were run"]
