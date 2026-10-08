"""Secret detection and redaction.

Detection runs on added lines only. Redaction runs on *every* excerpt and diff
line that leaves the analysis core (reports, exports, model prompts), so a
secret found in a change is never copied into a report or sent to an AI
provider.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SecretPattern:
    name: str
    regex: re.Pattern[str]
    group: int = 0
    provider_specific: bool = True


_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    SecretPattern("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b")),
    SecretPattern("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,255}\b")),
    SecretPattern("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    SecretPattern("Stripe secret key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    SecretPattern("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    SecretPattern("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{32,}\b")),
    SecretPattern("OpenAI API key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{40,}\b")),
    SecretPattern("Private key block", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    SecretPattern(
        "JSON Web Token",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ),
)

_GENERIC_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(?P<key>[A-Za-z0-9_\-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|auth)[A-Za-z0-9_\-]*)
    ["']?\s*(?::|=|:=|=>)\s*
    (?P<quote>["'`])(?P<value>[^"'`\s]{8,200})(?P=quote)
    """
)
_PLACEHOLDER_HINTS = (
    "example", "changeme", "change_me", "your_", "your-", "xxx", "placeholder", "dummy", "sample",
    "<", ">", "${", "{{", "todo", "redacted", "****", "process.env", "os.environ", "getenv", "none",
    "null", "undefined",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class SecretMatch:
    kind: str
    start: int
    end: int
    provider_specific: bool
    masked: str


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def mask(value: str) -> str:
    keep = 4 if len(value) > 12 else 2
    return value[:keep] + "*" * min(max(len(value) - keep, 4), 24)


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    if any(hint in lowered for hint in _PLACEHOLDER_HINTS):
        return True
    return len(set(value)) < 6


def find_secrets(line: str) -> list[SecretMatch]:
    matches: list[SecretMatch] = []
    taken: list[tuple[int, int]] = []
    for pattern in _PATTERNS:
        for m in pattern.regex.finditer(line):
            start, end = m.span(pattern.group)
            if any(s < end and start < e for s, e in taken):
                continue
            taken.append((start, end))
            matches.append(
                SecretMatch(pattern.name, start, end, True, mask(m.group(pattern.group)))
            )
    for m in _GENERIC_ASSIGNMENT.finditer(line):
        start, end = m.span("value")
        value = m.group("value")
        if any(s < end and start < e for s, e in taken):
            continue
        if _looks_like_placeholder(value) or shannon_entropy(value) < 3.0:
            continue
        taken.append((start, end))
        matches.append(
            SecretMatch(
                f"High-entropy value assigned to '{m.group('key')}'", start, end, False, mask(value)
            )
        )
    return sorted(matches, key=lambda s: s.start)


def redact(text: str) -> str:
    """Mask every detected secret in ``text`` (line by line)."""
    if not text:
        return text
    out_lines: list[str] = []
    for line in text.split("\n"):
        found = find_secrets(line)
        if not found:
            out_lines.append(line)
            continue
        pieces: list[str] = []
        cursor = 0
        for s in found:
            pieces.append(line[cursor : s.start])
            pieces.append(s.masked)
            cursor = s.end
        pieces.append(line[cursor:])
        out_lines.append("".join(pieces))
    return "\n".join(out_lines)
