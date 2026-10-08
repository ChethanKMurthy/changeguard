"""Matching predictions to labels.

A prediction matches a label when the category is identical, the file is
identical, and the line ranges overlap within ``LINE_TOLERANCE`` (a label
without lines matches any prediction in the file). Matching is one-to-one
(maximum bipartite matching), so one finding cannot satisfy two labels and two
duplicate findings cannot both be true positives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from changeguard.evaluation.dataset import Acceptable, Case, Label

LINE_TOLERANCE = 3


@dataclass(frozen=True, slots=True)
class Prediction:
    id: str
    rule_id: str
    category: str
    kind: str
    severity: str
    confidence: str
    file: str
    start_line: int | None
    end_line: int | None
    title: str

    @property
    def signature(self) -> str:
        return f"{self.rule_id}@{self.file}:{self.start_line or 0}"


@dataclass(slots=True)
class CaseResult:
    case_id: str
    split: str
    negative: bool
    language: str
    difficulty: str
    true_positives: list[tuple[str, Prediction]] = field(
        default_factory=list
    )  # (label id, prediction)
    false_positives: list[Prediction] = field(default_factory=list)
    acceptable: list[Prediction] = field(default_factory=list)
    false_negatives: list[Label] = field(default_factory=list)
    predictions: int = 0
    unsupported: list[str] = field(default_factory=list)  # finding ids with unverifiable evidence
    duration_ms: float = 0.0
    ai: dict[str, object] = field(default_factory=dict)
    error: str | None = None


def _overlap(a: tuple[int, int] | None, start: int | None, end: int | None) -> bool:
    if a is None:
        return True
    if start is None:
        return False
    lo, hi = a
    end = end if end is not None else start
    return start <= hi + LINE_TOLERANCE and lo - LINE_TOLERANCE <= end


def matches(label: Label, p: Prediction) -> bool:
    return (
        p.category == label.category.value
        and p.file == label.file
        and _overlap(label.lines, p.start_line, p.end_line)
    )


def accepted_by(acceptable: list[Acceptable], p: Prediction) -> bool:
    for a in acceptable:
        if a.category.value != p.category:
            continue
        if a.file is not None and a.file != p.file:
            continue
        if not _overlap(a.lines, p.start_line, p.end_line):
            continue
        return True
    return False


def match_case(case: Case, predictions: list[Prediction]) -> CaseResult:
    result = CaseResult(
        case.id,
        case.split,
        case.negative,
        case.language,
        case.difficulty,
        predictions=len(predictions),
    )
    labels = case.expected
    candidates = {
        i: [j for j, p in enumerate(predictions) if matches(label, p)]
        for i, label in enumerate(labels)
    }
    owner: dict[int, int] = {}  # prediction index -> label index

    def augment(label_index: int, seen: set[int]) -> bool:
        for pred_index in candidates[label_index]:
            if pred_index in seen:
                continue
            seen.add(pred_index)
            if pred_index not in owner or augment(owner[pred_index], seen):
                owner[pred_index] = label_index
                return True
        return False

    for i in range(len(labels)):
        augment(i, set())
    matched_labels = set(owner.values())
    for pred_index, label_index in sorted(owner.items(), key=lambda kv: kv[1]):
        result.true_positives.append((labels[label_index].id, predictions[pred_index]))
    for j, p in enumerate(predictions):
        if j in owner:
            continue
        if accepted_by(case.acceptable, p) or any(matches(label, p) for label in labels):
            # A duplicate of an already-matched label is neither rewarded nor penalised.
            result.acceptable.append(p)
        else:
            result.false_positives.append(p)
    result.false_negatives = [label for i, label in enumerate(labels) if i not in matched_labels]
    return result
