"""Dependency manifest analysis (requirements*.txt, pyproject.toml, package.json)."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import PurePosixPath

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.workspace import ChangedFile
from changeguard.report.models import Confidence, EvidenceType, Location, Severity, SuggestedTest

_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*((?:[<>=!~]=?|===)\s*[^;#\s][^;#]*)?"
)
_JSON_DEP_LINE = re.compile(r'^\s*"(@?[A-Za-z0-9][\w.\-/]*)"\s*:\s*"([^"]+)"\s*,?\s*$')
_NPM_SPEC = re.compile(r"^(?:[\^~<>=*]|\d|workspace:|npm:|latest|next|git\+|github:|https?:|file:)")
_IMPORT_ALIASES = {
    "pyyaml": "yaml", "beautifulsoup4": "bs4", "pillow": "PIL", "scikit-learn": "sklearn",
    "python-dateutil": "dateutil", "opencv-python": "cv2", "protobuf": "google.protobuf",
    "attrs": "attr", "python-dotenv": "dotenv", "psycopg2-binary": "psycopg2", "pyjwt": "jwt",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class DepChange:
    name: str
    before: str | None
    after: str | None
    ecosystem: str


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_manifest(path: str) -> str | None:
    name = PurePosixPath(path).name
    if name == "package.json":
        return "npm"
    if name == "pyproject.toml":
        return "pyproject"
    if re.match(r"^requirements[\w.-]*\.(txt|in)$", name):
        return "requirements"
    return None


def parse_requirements(text: str) -> dict[str, str]:
    deps: dict[str, str] = {}
    for raw in text.split("\n"):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+")) or "://" in line:
            continue  # options (-r/-e/--hash) and direct URL references
        m = _REQ_LINE.match(line)
        if m:
            deps[_norm(m.group(1))] = (m.group(3) or "").replace(" ", "")
    return deps


def parse_pyproject(text: str) -> dict[str, str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    deps: dict[str, str] = {}
    project = data.get("project", {})
    entries: list[str] = list(project.get("dependencies", []) or [])
    for group in (project.get("optional-dependencies", {}) or {}).values():
        entries += list(group or [])
    for group in (data.get("dependency-groups", {}) or {}).values():
        entries += [e for e in (group or []) if isinstance(e, str)]
    for entry in entries:
        m = _REQ_LINE.match(entry)
        if m:
            deps[_norm(m.group(1))] = (m.group(3) or "").replace(" ", "")
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
    for name, spec in poetry.items():
        if name.lower() != "python":
            deps[_norm(name)] = (
                spec
                if isinstance(spec, str)
                else str(spec.get("version", ""))
                if isinstance(spec, dict)
                else ""
            )
    return deps


def parse_package_json(text: str) -> dict[str, str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    deps: dict[str, str] = {}
    if not isinstance(data, dict):
        return deps
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(section)
        if isinstance(block, dict):
            for name, spec in block.items():
                deps[str(name)] = str(spec)
    return deps


_PARSERS = {
    "npm": parse_package_json,
    "pyproject": parse_pyproject,
    "requirements": parse_requirements,
}


def _from_lines(kind: str, lines: list[str]) -> dict[str, str]:
    deps: dict[str, str] = {}
    for line in lines:
        if kind == "npm":
            m = _JSON_DEP_LINE.match(line)
            if m and _NPM_SPEC.match(m.group(2)):
                deps[m.group(1)] = m.group(2)
        elif kind == "requirements":
            deps.update(parse_requirements(line))
        else:
            m = re.match(r'^\s*"([^"]+)"\s*,?\s*$', line)
            if m:
                rm = _REQ_LINE.match(m.group(1))
                if rm:
                    deps[_norm(rm.group(1))] = (rm.group(3) or "").replace(" ", "")
    return deps


def _major(spec: str | None) -> int | None:
    if not spec:
        return None
    m = re.search(r"(\d+)", spec)
    return int(m.group(1)) if m else None


def _pinned(spec: str | None) -> bool:
    if not spec:
        return False
    return spec.startswith("==") or bool(re.fullmatch(r"\d+(\.\d+){1,3}", spec))


def manifest_changes(cf: ChangedFile) -> list[DepChange]:
    kind = _is_manifest(cf.path)
    if kind is None:
        return []
    parser = _PARSERS[kind]
    if cf.full_context or cf.base_text is not None or cf.head_text is not None:
        before = parser(cf.base_text) if cf.base_text else {}
        after = parser(cf.head_text) if cf.head_text else {}
    else:
        before = _from_lines(
            kind, [ln.content for h in cf.diff.hunks for ln in h.lines if ln.kind == "del"]
        )
        after = _from_lines(
            kind, [ln.content for h in cf.diff.hunks for ln in h.lines if ln.kind == "add"]
        )
    ecosystem = "npm" if kind == "npm" else "pypi"
    changes: list[DepChange] = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b != a:
            changes.append(DepChange(name, b, a, ecosystem))
    return changes


def _line_of(cf: ChangedFile, name: str, side: str) -> int | None:
    kind = "add" if side == "head" else "del"
    needle = re.compile(rf"(^|[\"'\s]){re.escape(name)}([\"'\s\[<>=!~;]|$)", re.IGNORECASE)
    for h in cf.diff.hunks:
        for ln in h.lines:
            number = ln.new_lineno if side == "head" else ln.old_lineno
            if ln.kind == kind and number and needle.search(ln.content.replace("_", "-")):
                return number
    return None


def analyze_dependencies(ctx: AnalysisContext) -> dict[str, int]:
    stats = {"manifests": 0, "changes": 0}
    for cf in ctx.files:
        changes = manifest_changes(cf)
        if _is_manifest(cf.path):
            stats["manifests"] += 1
        stats["changes"] += len(changes)
        if cf.base_text is None and cf.old_path is None and len(changes) > 3:
            _report_new_manifest(ctx, cf, changes)
            continue
        for change in changes:
            _report(ctx, cf, change)
    return stats


def _report_new_manifest(ctx: AnalysisContext, cf: ChangedFile, changes: list[DepChange]) -> None:
    """A brand-new manifest: one aggregated finding instead of one per dependency."""
    names = [c.name for c in changes]
    ev = ctx.code_evidence(
        cf.path,
        1,
        min(len(cf.added) or 1, 20),
        type=EvidenceType.DEPENDENCY,
        title=f"New manifest {cf.path}",
        source="manifest diff",
        data={"packages": names},
        context=0,
    )
    ctx.add_finding(
        "CG-DEP-002",
        title=f"New manifest {cf.path} adds {len(changes)} dependencies",
        description=f"{cf.path} is new and declares: {', '.join(names[:12])}{' …' if len(names) > 12 else ''}.",
        location=Location(file=cf.path, start_line=1, end_line=1),
        evidence_ids=[ev],
        failure_scenario="Unreviewed third-party packages enter the supply chain with a routine install.",
        suggested_test=SuggestedTest(
            description="Audit the new dependencies (`pip-audit` / `npm audit`) and commit a lockfile.",
            kind="review",
        ),
        confidence=Confidence.HIGH,
    )


def _evidence(ctx: AnalysisContext, cf: ChangedFile, change: DepChange) -> str | None:
    side = "head" if change.after is not None else "base"
    line = _line_of(cf, change.name, side)
    data = {
        "package": change.name,
        "before": change.before,
        "after": change.after,
        "ecosystem": change.ecosystem,
    }
    if line is None:
        return ctx.evidence.add(
            EvidenceType.DEPENDENCY, f"{change.name}: {change.before or '∅'} → {change.after or '∅'}",
            source="manifest diff", file=cf.path, data=data,
        )  # fmt: skip
    return ctx.code_evidence(
        cf.path, line, line, side="head" if side == "head" else "base", type=EvidenceType.DEPENDENCY,
        title=f"{change.name}: {change.before or '∅'} → {change.after or '∅'}", source="manifest diff", data=data, context=1,
    )  # fmt: skip


def _report(ctx: AnalysisContext, cf: ChangedFile, change: DepChange) -> None:
    ev = _evidence(ctx, cf, change)
    line = _line_of(cf, change.name, "head" if change.after is not None else "base")
    loc = Location(
        file=cf.path,
        start_line=line,
        end_line=line,
        side="head" if change.after is not None else "base",
    )
    name = change.name
    if change.before is None:
        ctx.add_finding(
            "CG-DEP-002",
            title=f"New dependency `{name}` ({change.after or 'unpinned'})",
            description=f"`{name}` was added to {cf.path}.",
            location=loc,
            evidence_ids=[ev],
            failure_scenario="A typo-squatted, unmaintained, or vulnerable package enters production through a "
            "routine install.",
            suggested_test=SuggestedTest(
                description=f"Check `{name}`'s maintainers, licence, and advisories (e.g. `pip-audit` / `npm audit`) "
                "and pin a version.",
                kind="review",
            ),
            confidence=Confidence.HIGH,
            discriminator=name,
        )
        return
    if change.after is None:
        importers = _importers(ctx, change)
        ctx.add_finding(
            "CG-DEP-003",
            title=f"Dependency `{name}` removed" + (" but still imported" if importers else ""),
            description=f"`{name}` was removed from {cf.path}."
            + (
                f" It is still imported in {len(importers)} place(s), e.g. {importers[0][0]}:{importers[0][1]}."
                if importers
                else ""
            ),
            location=loc,
            evidence_ids=[ev]
            + [
                ctx.code_evidence(
                    p,
                    n,
                    n,
                    title=f"`{name}` imported at {p}:{n}",
                    type=EvidenceType.SYMBOL_REFERENCE,
                    context=0,
                )
                for p, n in importers[:4]
            ],
            failure_scenario="A clean install (CI, new container image) no longer provides the package, so the first "
            "import raises ImportError / module-not-found.",
            suggested_test=SuggestedTest(
                description="Build from a clean environment (fresh virtualenv / `npm ci`) and run the import smoke test.",
                kind="integration",
            ),
            severity=Severity.HIGH if importers else Severity.LOW,
            confidence=Confidence.MEDIUM,
            discriminator=name,
        )
        return
    before_major, after_major = _major(change.before), _major(change.after)
    if before_major is not None and after_major is not None and before_major != after_major:
        direction = "upgrade" if after_major > before_major else "downgrade"
        ctx.add_finding(
            "CG-DEP-001",
            title=f"Major {direction} of `{name}`: {change.before} → {change.after}",
            description=f"`{name}` moves from major version {before_major} to {after_major}.",
            location=loc,
            evidence_ids=[ev],
            failure_scenario=f"APIs of `{name}` used by this code were removed or changed in v{after_major}; failures "
            "appear at import time or on the first call to a changed API.",
            suggested_test=SuggestedTest(
                description=f"Read `{name}`'s migration guide and run the full test suite plus a smoke test of the "
                f"code paths that use `{name}`.",
                kind="integration",
            ),
            confidence=Confidence.HIGH,
            discriminator=name,
        )
    elif _pinned(change.before) and not _pinned(change.after):
        ctx.add_finding(
            "CG-DEP-004",
            title=f"Version constraint for `{name}` loosened: {change.before} → {change.after}",
            description=f"`{name}` was pinned and now accepts a range.",
            location=loc,
            evidence_ids=[ev],
            failure_scenario="A future install resolves a newer, untested release and behaviour changes without any "
            "code change.",
            suggested_test=SuggestedTest(
                description="Keep a lockfile in version control and test upgrades explicitly.",
                kind="review",
            ),
            confidence=Confidence.HIGH,
            discriminator=name,
        )


def _importers(ctx: AnalysisContext, change: DepChange) -> list[tuple[str, int]]:
    if not ctx.full_context:
        return []
    if change.ecosystem == "pypi":
        module = _IMPORT_ALIASES.get(change.name, change.name.replace("-", "_"))
        pattern = re.compile(
            rf"^\s*(from\s+{re.escape(module)}(\.|\s)|import\s+{re.escape(module)}(\.|\s|$|,))"
        )
        suffixes: tuple[str, ...] = (".py",)
    else:
        pattern = re.compile(
            rf"""(from\s+|require\(\s*)['"]{re.escape(change.name)}(/[^'"]*)?['"]"""
        )
        suffixes = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
    hits: list[tuple[str, int]] = []
    for path, text in sorted(ctx.workspace.head_repo.items()):
        if not path.endswith(suffixes):
            continue
        for i, line in enumerate(text.split("\n"), start=1):
            if pattern.search(line):
                hits.append((path, i))
                break
    return hits
