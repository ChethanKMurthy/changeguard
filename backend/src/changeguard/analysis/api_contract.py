"""API-contract analysis: signature changes, removed symbols, and their callers."""

from __future__ import annotations

from changeguard.analysis.codegen import regression_test
from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.references import Reference, RepositoryIndex, check_call
from changeguard.analysis.structure import SymbolChange
from changeguard.ingest.diff_parser import FileStatus
from changeguard.languages.model import LanguageId, Symbol
from changeguard.report.models import (
    Confidence,
    EvidenceType,
    FindingKind,
    Location,
    Severity,
    SuggestedTest,
)

MAX_CALL_EVIDENCE = 8


def analyze_api_contract(ctx: AnalysisContext, repo: RepositoryIndex | None) -> dict[str, int]:
    stats = {
        "signature_changes": 0,
        "breaking": 0,
        "call_sites_checked": 0,
        "incompatible": 0,
        "removed_checked": 0,
    }
    for sc in ctx.symbol_changes:
        if sc.is_test or sc.kind == "type":
            continue
        if (
            sc.change in ("modified", "renamed")
            and sc.signature_diff is not None
            and sc.after is not None
        ):
            stats["signature_changes"] += 1
            _signature_findings(ctx, repo, sc, stats)
        if sc.change in ("removed", "renamed") and sc.before is not None and sc.kind != "test":
            stats["removed_checked"] += 1
            _removed_symbol_findings(ctx, repo, sc)
    if repo is not None:
        _moved_module_findings(ctx, repo)
        stats["blast_radius_symbols"] = _blast_radius(ctx, repo)
    return stats


MAX_BLAST_RADIUS_SYMBOLS = 60


def _blast_radius(ctx: AnalysisContext, repo: RepositoryIndex) -> int:
    """Count resolved callers of modified symbols that had no signature change (for the report)."""
    done = 0
    for sc in ctx.symbol_changes:
        if done >= MAX_BLAST_RADIUS_SYMBOLS:
            break
        if (
            sc.call_sites
            or sc.after is None
            or sc.change != "modified"
            or sc.kind not in ("function", "method", "class")
        ):
            continue
        refs = repo.references(sc.after, defined_in=sc.file, include_name_only=False)
        sc.call_sites = [r for r in refs if r.kind == "call"]
        done += 1
    return done


# -- signature changes ------------------------------------------------------------


def _signature_evidence(ctx: AnalysisContext, sc: SymbolChange) -> str | None:
    assert sc.after is not None and sc.signature_diff is not None
    before = (
        sc.before.signature.render(sc.before.name) if sc.before and sc.before.signature else None
    )
    after = sc.after.signature.render(sc.after.name) if sc.after.signature else None
    snippet = ctx.excerpt(sc.file, sc.after.signature_line, sc.after.signature_line, context=1)
    return ctx.evidence.add(
        EvidenceType.SIGNATURE_CHANGE,
        f"Signature of {sc.qualname} changed",
        source="tree-sitter structural diff",
        file=sc.file,
        start_line=sc.after.signature_line,
        end_line=sc.after.signature_line,
        side="head",
        excerpt=snippet[0] if snippet else None,
        excerpt_start_line=snippet[1] if snippet else None,
        highlight_lines=[sc.after.signature_line],
        data={
            "before": before,
            "after": after,
            "changes": sc.signature_diff.describe(),
            "breaking": sc.signature_diff.breaking,
            "base_line": sc.before.signature_line if sc.before else None,
        },
    )


def _call_evidence(
    ctx: AnalysisContext, ref: Reference, problems: list[str] | None = None, *, note: str = ""
) -> str | None:
    title = f"Call site {ref.file}:{ref.line}"
    if ref.call is not None and ref.call.enclosing:
        title += f" in {ref.call.enclosing}"
    data: dict[str, object] = {"resolution": ref.resolution, "via": ref.via}
    if ref.call is not None:
        data["call"] = ref.call.text
    if problems:
        data["problems"] = problems
    if note:
        data["note"] = note
    return ctx.code_evidence(
        ref.file,
        ref.line,
        ref.call.end_line if ref.call is not None else ref.line,
        title=title,
        type=EvidenceType.CALL_SITE,
        source="repository snapshot (tree-sitter)",
        data=data,
        context=1,
    )


def _signature_findings(
    ctx: AnalysisContext, repo: RepositoryIndex | None, sc: SymbolChange, stats: dict[str, int]
) -> None:
    diff = sc.signature_diff
    after = sc.after
    assert diff is not None and after is not None and after.signature is not None
    sig_ev = _signature_evidence(ctx, sc)
    location = Location(
        file=sc.file,
        start_line=after.signature_line,
        end_line=after.signature_line,
        symbol=sc.qualname,
    )
    refs: list[Reference] = []
    if repo is not None and not sc.approximate:
        refs = [
            r
            for r in repo.references(after, defined_in=sc.file)
            if r.kind == "call" and r.call is not None
        ]
    sc.call_sites = list(refs)
    stats["call_sites_checked"] += len(refs)

    incompatible: list[tuple[Reference, list[str]]] = []
    for ref in refs:
        assert ref.call is not None
        drop = ref.drop_first if after.kind == "method" else False
        if ref.via == "constructor":
            drop = (
                sc.language is LanguageId.PYTHON
            )  # Python __init__ binds self; JS constructors have no receiver param
        problems = check_call(after.signature, ref.call, language=sc.language, drop_first=drop)
        if problems:
            incompatible.append((ref, problems))
    sc.incompatible_calls = list(incompatible)
    stats["incompatible"] += len(incompatible)
    changes = "; ".join(diff.describe())

    if diff.breaking:
        stats["breaking"] += 1
    if incompatible:
        resolved = [x for x in incompatible if x[0].resolution == "resolved"]
        typed = sc.language in (LanguageId.PYTHON, LanguageId.TYPESCRIPT)
        evidence = [sig_ev] + [
            _call_evidence(ctx, r, p) for r, p in incompatible[:MAX_CALL_EVIDENCE]
        ]
        first_ref, first_problems = incompatible[0]
        failure = (
            f"{first_ref.file}:{first_ref.line} still calls `{after.name}` the old way: it "
            f"{first_problems[0]}. "
            + (
                "Python raises TypeError when that line runs."
                if sc.language is LanguageId.PYTHON
                else "TypeScript compilation fails."
                if sc.language is LanguageId.TYPESCRIPT
                else "JavaScript silently passes `undefined` for the missing argument."
            )
        )
        ctx.add_finding(
            "CG-API-001",
            title=f"{len(incompatible)} call site(s) incompatible with new signature of `{after.name}`",
            description=f"`{sc.qualname}` changed ({changes}). {len(incompatible)} of {len(refs)} call site(s) in the "
            f"repository no longer match the new signature.",
            location=location,
            evidence_ids=evidence,
            failure_scenario=failure,
            suggested_test=SuggestedTest(
                description=f"Update the incompatible callers, then add a regression test that calls `{after.name}` "
                "the way those callers do.",
                kind="regression",
                code=regression_test(
                    after,
                    sc.file,
                    sc.language,
                    purpose="matches_callers",
                    body_comment="mirror the argument shape used at the call sites listed in the evidence",
                ),
                language=sc.language.value,
            ),
            severity=Severity.HIGH if typed or resolved else Severity.MEDIUM,
            confidence=Confidence.HIGH if resolved else Confidence.MEDIUM,
            kind=FindingKind.DETERMINISTIC if (resolved and typed) else FindingKind.HEURISTIC,
            related_symbols=[sc.qualname],
            tags=["signature", "callers"],
        )
    elif diff.breaking and after.is_public:
        note = (
            "call sites could not be checked because no repository snapshot was provided"
            if repo is None or sc.approximate
            else f"all {len(refs)} call site(s) found in the repository are compatible"
            if refs
            else "no call sites were found in the repository"
        )
        ctx.add_finding(
            "CG-API-003",
            title=f"Breaking signature change to public `{after.name}`",
            description=f"`{sc.qualname}` changed ({changes}); {note}.",
            location=location,
            evidence_ids=[sig_ev],
            failure_scenario=f"Any caller outside the analysed code that uses the previous signature of `{after.name}` "
            "breaks (other services, packages, notebooks, or scripts).",
            suggested_test=SuggestedTest(
                description="Search dependent repositories for callers, and add a test that pins the new public signature.",
                kind="regression",
                code=regression_test(
                    after,
                    sc.file,
                    sc.language,
                    purpose="new_signature",
                    body_comment="pin the new public signature so future changes are deliberate",
                ),
                language=sc.language.value,
            ),
            confidence=Confidence.MEDIUM
            if repo is not None and not sc.approximate
            else Confidence.LOW,
            related_symbols=[sc.qualname],
            tags=["signature", "public-api"],
        )

    if diff.became_async:
        sync_callers = [r for r in refs if r.call is not None and not r.call.awaited]
        if sync_callers:
            any_resolved = any(r.resolution == "resolved" for r in sync_callers)
            ctx.add_finding(
                "CG-API-004",
                title=f"`{after.name}` became async but {len(sync_callers)} caller(s) do not await it",
                description=f"`{sc.qualname}` is now async. These call sites call it without `await`, so they receive "
                "a coroutine/promise instead of the result.",
                location=location,
                evidence_ids=[sig_ev]
                + [
                    _call_evidence(ctx, r, ["call is not awaited"])
                    for r in sync_callers[:MAX_CALL_EVIDENCE]
                ],
                failure_scenario=f"{sync_callers[0].file}:{sync_callers[0].line} uses the return value of `{after.name}` "
                "as if it were the result; the coroutine is never executed (Python warns 'coroutine was never "
                "awaited') and downstream code operates on the wrong type.",
                suggested_test=SuggestedTest(
                    description=f"Test each caller of `{after.name}` end-to-end so the await chain is exercised.",
                    kind="integration",
                    language=sc.language.value,
                ),
                confidence=Confidence.HIGH if any_resolved else Confidence.MEDIUM,
                kind=FindingKind.DETERMINISTIC
                if any_resolved and sc.language is LanguageId.PYTHON
                else FindingKind.HEURISTIC,
                related_symbols=[sc.qualname],
                tags=["async"],
            )

    if diff.default_changed:
        name, old, new = diff.default_changed[0]
        relying = [r for r in refs if r.call is not None and _omits(after, r, name)]
        ctx.add_finding(
            "CG-API-005",
            title=f"Default of `{name}` in `{after.name}` changed from `{old}` to `{new}`",
            description=f"Callers that omit `{name}` now get `{new}` instead of `{old}`."
            + (f" {len(relying)} call site(s) in the repository omit it." if relying else ""),
            location=location,
            evidence_ids=[sig_ev]
            + [
                _call_evidence(ctx, r, note=f"omits `{name}`; relies on the default")
                for r in relying[:MAX_CALL_EVIDENCE]
            ],
            failure_scenario=f"A caller relying on the old default `{old}` silently gets behaviour for `{new}`"
            + (f", e.g. {relying[0].file}:{relying[0].line}." if relying else "."),
            suggested_test=SuggestedTest(
                description=f"Add a test that calls `{after.name}` without `{name}` and asserts the intended default behaviour.",
                kind="unit",
                code=regression_test(
                    after,
                    sc.file,
                    sc.language,
                    purpose=f"default_{name}",
                    body_comment=f"omit `{name}` and assert the behaviour expected for the default `{new}`",
                ),
                language=sc.language.value,
            ),
            severity=Severity.MEDIUM if relying or after.is_public else Severity.LOW,
            confidence=Confidence.MEDIUM,
            related_symbols=[sc.qualname],
            tags=["default-value"],
            discriminator=name,
        )

    if diff.returns_changed and sc.language is not LanguageId.JAVASCRIPT:
        old_ret, new_ret = diff.returns_changed
        ctx.add_finding(
            "CG-API-006",
            title=f"Return type of `{after.name}` changed",
            description=f"Return annotation changed from `{old_ret or 'none'}` to `{new_ret or 'none'}`.",
            location=location,
            evidence_ids=[sig_ev],
            failure_scenario="Callers that use the result as the previous type (attribute access, arithmetic, "
            "serialisation) fail or behave differently.",
            suggested_test=SuggestedTest(
                description=f"Assert the type and shape of `{after.name}`'s return value in a unit test.",
                kind="unit",
                language=sc.language.value,
            ),
            confidence=Confidence.MEDIUM,
            related_symbols=[sc.qualname],
            tags=["return-type"],
        )


def _omits(symbol: Symbol, ref: Reference, param_name: str) -> bool:
    assert ref.call is not None and symbol.signature is not None
    params = list(symbol.signature.params)
    binds_receiver = ref.drop_first or (
        ref.via == "constructor" and symbol.file.endswith((".py", ".pyi"))
    )
    if binds_receiver and params:
        params = params[1:]
    positional = [p.name for p in params if p.kind in ("positional_only", "positional_or_keyword")]
    if ref.call.star_args or ref.call.star_kwargs:
        return False
    if param_name in ref.call.keywords:
        return False
    return not (param_name in positional and positional.index(param_name) < ref.call.positional)


# -- removed symbols ------------------------------------------------------------


def _removed_symbol_findings(
    ctx: AnalysisContext, repo: RepositoryIndex | None, sc: SymbolChange
) -> None:
    before = sc.before
    assert before is not None
    base_path = before.file
    def_snippet = ctx.excerpt(
        base_path,
        before.start_line,
        min(before.end_line, before.start_line + 4),
        side="base",
        context=0,
    )
    def_ev = ctx.evidence.add(
        EvidenceType.SYMBOL_REFERENCE,
        f"{'Renamed' if sc.change == 'renamed' else 'Removed'} definition of {before.qualname}",
        source="tree-sitter structural diff",
        file=base_path,
        start_line=before.start_line,
        end_line=before.end_line,
        side="base",
        excerpt=def_snippet[0] if def_snippet else None,
        excerpt_start_line=def_snippet[1] if def_snippet else None,
        highlight_lines=[before.signature_line],
        data={"renamed_to": sc.qualname if sc.change == "renamed" else None},
    )
    if repo is None or sc.approximate:
        return
    refs = repo.references(before, defined_in=base_path, include_name_only=False)
    # Same-file references to the removed name are reported by static analysis (F821).
    refs = [r for r in refs if r.file != base_path or r.kind == "import"]
    imports = [r for r in refs if r.kind == "import"]
    uses = [r for r in refs if r.kind != "import"]
    label = f"renamed to `{sc.name}`" if sc.change == "renamed" else "removed"
    old_name = before.name
    if refs:
        first = refs[0]
        is_py = sc.language is LanguageId.PYTHON
        failure = (
            f"{first.file}:{first.line} imports `{old_name}`, which no longer exists: "
            + (
                "the module fails to import with ImportError, taking down everything that imports it."
                if is_py
                else "the build fails (TypeScript) or the import resolves to undefined (CommonJS)."
            )
            if imports
            else f"{first.file}:{first.line} references `{old_name}`, which no longer exists: "
            + (
                "AttributeError/NameError when that line runs."
                if is_py
                else "TypeError when that line runs."
            )
        )
        ctx.add_finding(
            "CG-API-002",
            title=f"`{old_name}` was {label} but is still referenced in {len({r.file for r in refs})} file(s)",
            description=f"`{before.qualname}` was {label}; {len(imports)} import(s) and {len(uses)} other reference(s) "
            "still use the old name.",
            location=Location(
                file=base_path,
                start_line=before.signature_line,
                end_line=before.signature_line,
                side="base",
                symbol=before.qualname,
            ),
            evidence_ids=[def_ev]
            + [
                _call_evidence(ctx, r, note="references the removed name")
                for r in refs[:MAX_CALL_EVIDENCE]
            ],
            failure_scenario=failure,
            suggested_test=SuggestedTest(
                description=f"Update the remaining references to `{old_name}`; an import smoke test (importing every "
                "module) catches this class of break in CI.",
                kind="static",
                code=_import_smoke_test(sc.language),
                language=sc.language.value,
            ),
            severity=Severity.CRITICAL if imports else Severity.HIGH,
            confidence=Confidence.HIGH,
            related_symbols=[before.qualname],
            tags=["removed-symbol"],
        )
    elif (
        sc.change == "removed"
        and before.is_public
        and (before.kind != "variable" or before.name.isupper())
    ):
        cf = ctx.workspace.file(sc.file)
        if cf is not None and cf.status is FileStatus.DELETED and before.kind == "variable":
            return
        ctx.add_finding(
            "CG-API-007",
            title=f"Public `{old_name}` removed",
            description=f"`{before.qualname}` was removed. No references remain in the analysed repository.",
            location=Location(
                file=base_path,
                start_line=before.signature_line,
                end_line=before.signature_line,
                side="base",
                symbol=before.qualname,
            ),
            evidence_ids=[def_ev],
            failure_scenario=f"Consumers outside this repository that import `{old_name}` break on upgrade.",
            suggested_test=SuggestedTest(
                description="If this module is a published API, deprecate before removal and note it in the changelog.",
                kind="review",
            ),
            confidence=Confidence.MEDIUM,
            related_symbols=[before.qualname],
            tags=["public-api"],
        )


def _moved_module_findings(ctx: AnalysisContext, repo: RepositoryIndex) -> None:
    """Imports that still point at a deleted or renamed module."""
    if not ctx.full_context:
        return
    for removed_path in sorted(repo.removed_paths):
        stem = removed_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        hits: list[Reference] = []
        for path in repo.candidate_files([stem]):
            idx = repo.index(path)
            if idx is None:
                continue
            for b in idx.imports:
                resolved = repo.resolve(b)
                if resolved is not None and resolved.target == removed_path:
                    hits.append(
                        Reference(
                            path, b.line, "import", "resolved", binding=b, via="module import"
                        )
                    )
        if not hits:
            continue
        cf = next((f for f in ctx.files if f.old_path == removed_path), None)
        moved_to = cf.path if cf is not None and cf.status is FileStatus.RENAMED else None
        evidence = [
            _call_evidence(ctx, r, note="imports a module that no longer exists at this path")
            for r in hits[:MAX_CALL_EVIDENCE]
        ]
        ctx.add_finding(
            "CG-API-002",
            title=f"Module `{removed_path}` was {'moved' if moved_to else 'deleted'} but is still imported",
            description=f"{len(hits)} import(s) still resolve to `{removed_path}`"
            + (f", which was renamed to `{moved_to}`." if moved_to else ", which was deleted."),
            location=Location(
                file=moved_to or removed_path,
                start_line=None,
                end_line=None,
                side="head" if moved_to else "base",
            ),
            evidence_ids=evidence,
            failure_scenario=f"{hits[0].file}:{hits[0].line} fails at import time (ImportError / module not found).",
            suggested_test=SuggestedTest(
                description="Update the imports; an import smoke test catches moved modules.",
                kind="static",
                code=_import_smoke_test(ctx.files[0].language or LanguageId.PYTHON),
            ),
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            tags=["moved-module"],
            discriminator=removed_path,
        )


def _import_smoke_test(language: LanguageId) -> str:
    if language is LanguageId.PYTHON:
        return (
            "import importlib\n"
            "import pkgutil\n\n"
            "import your_package  # replace with the top-level package\n\n\n"
            "def test_every_module_imports():\n"
            '    for module in pkgutil.walk_packages(your_package.__path__, your_package.__name__ + "."):\n'
            "        importlib.import_module(module.name)\n"
        )
    return "// Run the TypeScript compiler in CI:\n//   npx tsc --noEmit\n"
