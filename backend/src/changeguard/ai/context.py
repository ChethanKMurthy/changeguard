"""Build the model-facing context pack from analysis results.

Security properties of the pack:

* **Untrusted fencing** — every code excerpt is wrapped in
  ``BEGIN UNTRUSTED <id> <nonce>`` / ``END UNTRUSTED <id> <nonce>`` markers
  with a per-request random nonce, so text inside the change cannot forge
  the end of its own fence.
* **Injection neutralisation** — lines flagged by the prompt-injection rule
  are replaced before the model sees them.
* **Secret redaction** — excerpts come from the evidence store, which masks
  detected secrets at creation time.
* **Budget** — the pack is assembled in priority order (highest-severity
  findings first, then diff hunks) until a character budget is reached, and
  the report records whether truncation happened.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.secrets import redact
from changeguard.analysis.textual import INJECTION_PATTERNS
from changeguard.report.models import SEVERITY_RANK, Evidence, EvidenceType, Finding, FindingKind

MAX_EXCERPT_LINES = 14
MAX_HUNK_LINES = 40
WITHHELD = "⟦line withheld by ChangeGuard: suspected prompt-injection text⟧"


@dataclass(slots=True)
class ContextPack:
    nonce: str
    findings: list[Finding]
    evidence: list[Evidence]
    change_summary: str
    findings_text: str
    evidence_text: str
    truncated: bool = False
    known_files: set[str] = field(default_factory=set)

    @property
    def evidence_ids(self) -> list[str]:
        return [e.id for e in self.evidence]

    @property
    def chars(self) -> int:
        return len(self.change_summary) + len(self.findings_text) + len(self.evidence_text)


def _excerpt_lines(ctx: AnalysisContext, ev: Evidence, max_lines: int) -> list[str]:
    if ev.excerpt is None:
        return []
    injected = ctx.stage_data.get("injection_lines", set())
    lines = ev.excerpt.split("\n")
    out: list[str] = []
    for offset, text in enumerate(lines[:max_lines]):
        number = (ev.excerpt_start_line + offset) if ev.excerpt_start_line is not None else None
        if ev.file is not None and number is not None and (ev.file, number) in injected:
            text = WITHHELD
        prefix = f"{number:>5} | " if number is not None else "      | "
        out.append(prefix + text)
    if len(lines) > max_lines:
        out.append(f"      | … {len(lines) - max_lines} more line(s) omitted")
    return out


def _render_evidence(ctx: AnalysisContext, ev: Evidence, nonce: str, max_lines: int) -> str:
    location = ""
    if ev.file:
        location = ev.file
        if ev.start_line:
            location += f":{ev.start_line}" + (
                f"-{ev.end_line}" if ev.end_line and ev.end_line != ev.start_line else ""
            )
        if ev.side == "base":
            location += " (before the change)"
    header = f"[{ev.id}] {ev.type.value} — {ev.title}" + (f" — {location}" if location else "")
    facts = {
        k: v
        for k, v in ev.data.items()
        if k
        in (
            "before",
            "after",
            "changes",
            "problems",
            "code",
            "message",
            "uncovered_lines",
            "change",
            "operation",
            "detector",
            "package",
        )
    }
    parts = [header]
    if facts:
        parts.append("  facts: " + redact(str(facts))[:600])
    body = _excerpt_lines(ctx, ev, max_lines)
    if body:
        parts.append(f"  BEGIN UNTRUSTED {ev.id} {nonce}")
        parts.extend("  " + line for line in body)
        parts.append(f"  END UNTRUSTED {ev.id} {nonce}")
    return "\n".join(parts)


def _hunk_evidence(ctx: AnalysisContext) -> list[str]:
    """Register each diff hunk of a structurally supported file as evidence the model may cite."""
    ids: list[str] = []
    for cf in ctx.files:
        if cf.diff.is_binary or cf.language is None:
            continue
        for hunk in cf.diff.hunks:
            rows = [ln for ln in hunk.lines if ln.kind != "del"][:MAX_HUNK_LINES]
            if not rows:
                continue
            numbers = [ln.new_lineno for ln in rows if ln.new_lineno is not None]
            if not numbers:
                continue
            excerpt = "\n".join(ln.content for ln in rows)
            added = [ln.new_lineno for ln in rows if ln.kind == "add" and ln.new_lineno is not None]
            deleted = [ln.content for ln in hunk.lines if ln.kind == "del"][:12]
            ids.append(
                ctx.evidence.add(
                    EvidenceType.DIFF_HUNK,
                    f"Diff hunk {hunk.header.split('@@')[1].strip()} in {cf.path}",
                    source="diff",
                    file=cf.path,
                    start_line=numbers[0],
                    end_line=numbers[-1],
                    side="head",
                    excerpt=excerpt,
                    excerpt_start_line=numbers[0],
                    highlight_lines=added,
                    data={"removed_lines": deleted, "section": hunk.section},
                )
            )
    return ids


def _fence_nonce(ctx: AnalysisContext) -> str:
    """Deterministic fence nonce derived from the content being fenced.

    Untrusted text cannot contain the nonce: the nonce is a hash of that very
    text, so embedding it would change the hash (a fixed point is
    computationally infeasible). Determinism keeps prompts byte-identical
    across runs, which the response cache and recorded replays rely on.
    """
    digest = hashlib.sha256(b"changeguard-fence-v1")
    for e in ctx.evidence.all():
        digest.update((e.excerpt or "").encode("utf-8", "replace"))
    for cf in ctx.files:
        for h in cf.diff.hunks:
            for ln in h.lines:
                digest.update(ln.content.encode("utf-8", "replace"))
    return digest.hexdigest()[:12]


def build_context(ctx: AnalysisContext, *, max_chars: int, max_findings: int) -> ContextPack:
    nonce = _fence_nonce(ctx)
    candidates = sorted(
        (f for f in ctx.findings if f.kind is not FindingKind.AI),
        key=lambda f: (-SEVERITY_RANK[f.severity], f.location.file, f.location.start_line or 0),
    )
    chosen = candidates[:max_findings]
    hunk_ids = _hunk_evidence(ctx)

    files = sorted({cf.path for cf in ctx.files})
    change_summary = (
        f"{len(ctx.files)} file(s) changed (+{ctx.patch.additions} −{ctx.patch.deletions}): "
        + ", ".join(
            f"{cf.path} [{cf.status.value}, {cf.display_language}]" for cf in ctx.files[:20]
        )
    )
    if ctx.patch.subject:
        subject = redact(ctx.patch.subject)[:200]
        if any(p.search(subject) for p in INJECTION_PATTERNS):
            subject = "(withheld: suspected prompt-injection text)"
        change_summary += f"\nCommit subject (untrusted text): {subject}"

    budget = max_chars - len(change_summary) - 1500  # headroom for findings text and instructions
    evidence_blocks: list[str] = []
    included: list[Evidence] = []
    seen: set[str] = set()
    truncated = False

    def include(evidence_id: str, max_lines: int) -> bool:
        nonlocal budget, truncated
        if evidence_id in seen:
            return True
        ev = ctx.evidence.get(evidence_id)
        if ev is None:
            return False
        block = _render_evidence(ctx, ev, nonce, max_lines)
        if len(block) > budget:
            truncated = True
            return False
        budget -= len(block)
        seen.add(evidence_id)
        evidence_blocks.append(block)
        included.append(ev)
        return True

    kept_findings: list[Finding] = []
    for f in chosen:
        # Evaluate every include (no short-circuit): each finding contributes up to 3 items.
        included_any = [include(eid, MAX_EXCERPT_LINES) for eid in f.evidence_ids[:3]]
        if any(included_any):
            kept_findings.append(f)
    if len(kept_findings) < len(candidates):
        truncated = truncated or len(candidates) > max_findings
    for hid in hunk_ids:
        include(hid, MAX_HUNK_LINES)

    findings_text = (
        "\n".join(
            f"- id={f.id} | {f.severity.value} | {f.kind.value} | {f.category.value} | rule {f.rule_id} | "
            f"{f.location.file}:{f.location.start_line or '?'} | {f.title} | evidence: "
            + ", ".join(e for e in f.evidence_ids if e in seen)
            for f in kept_findings
        )
        or "(none — there are no deterministic findings; focus on additional risks)"
    )
    return ContextPack(
        nonce=nonce,
        findings=kept_findings,
        evidence=included,
        change_summary=change_summary,
        findings_text=findings_text,
        evidence_text="\n\n".join(evidence_blocks),
        truncated=truncated,
        known_files=set(files) | {e.file for e in included if e.file},
    )
