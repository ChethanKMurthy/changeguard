"""AST pattern rules evaluated on lines added by the change.

JavaScript/TypeScript has no single embeddable linter comparable to Ruff, so
the risk-relevant patterns are implemented directly over the tree-sitter AST.
A few Python checks Ruff does not cover (skipped tests, risky settings) live
here too. Only nodes that start on an *added* line are considered, so
pre-existing code is never blamed on the change.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from tree_sitter import Node

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.workspace import ChangedFile
from changeguard.languages.model import LanguageId
from changeguard.languages.registry import grammar_for_path, parse
from changeguard.languages.treeutil import line, text, walk
from changeguard.report.models import Confidence, EvidenceType, Location, Severity, SuggestedTest

_HTML_SINK_PROPERTIES = frozenset({"innerHTML", "outerHTML"})
_CONSOLE_METHODS = frozenset({"log", "debug", "trace", "dir", "table", "info"})
_FOCUS = frozenset(
    {"it.only", "test.only", "describe.only", "context.only", "suite.only", "fit", "fdescribe"}
)
_SKIP = frozenset(
    {
        "it.skip",
        "test.skip",
        "describe.skip",
        "context.skip",
        "suite.skip",
        "xit",
        "xdescribe",
        "xtest",
        "xcontext",
    }
)
_PY_SKIP_DECORATORS = re.compile(
    r"^(pytest\.mark\.(skip|skipif|xfail)|unittest\.(skip|skipIf|skipUnless|expectedFailure)|skip)\b"
)


@dataclass(slots=True)
class Match:
    rule_id: str
    line: int
    title: str
    detail: str
    severity: Severity | None = None
    confidence: Confidence = Confidence.HIGH


def _head_trees(cf: ChangedFile) -> Iterator[tuple[Node, Callable[[int], int]]]:
    """Yield (root, map_line) for the head revision or, in diff-only mode, each hunk fragment."""
    grammar = grammar_for_path(cf.path)
    if grammar is None:
        return
    if cf.head_text is not None:
        yield parse(cf.head_text, grammar).root_node, lambda n: n
        return
    for hunk in cf.diff.hunks:
        rows = [
            (ln.new_lineno, ln.content)
            for ln in hunk.lines
            if ln.kind != "del" and ln.new_lineno is not None
        ]
        if not rows:
            continue
        numbers = [n for n, _ in rows]
        fragment = textwrap.dedent("\n".join(c for _, c in rows))

        def remap(local: int, numbers: list[int] = numbers) -> int:
            return numbers[min(max(local, 1), len(numbers)) - 1]

        yield parse(fragment, grammar).root_node, remap


def analyze_patterns(ctx: AnalysisContext) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cf in ctx.files:
        if cf.language is None or cf.diff.is_binary or not cf.added:
            continue
        matches: list[Match] = []
        for root, remap in _head_trees(cf):
            if cf.language is LanguageId.PYTHON:
                matches += _python_matches(root, remap, cf)
                if not cf.full_context:
                    # Ruff needs complete files; on hunk fragments fall back to AST patterns.
                    matches += _python_fragment_matches(root, remap, cf)
            else:
                matches += _js_matches(root, remap, cf)
        matches = [m for m in matches if m.line in cf.added]
        for m in _dedupe(matches):
            _report(ctx, cf, m)
            counts[m.rule_id] = counts.get(m.rule_id, 0) + 1
    return counts


def _dedupe(matches: list[Match]) -> list[Match]:
    seen: set[tuple[str, int]] = set()
    out: list[Match] = []
    for m in sorted(matches, key=lambda m: (m.line, m.rule_id)):
        if (m.rule_id, m.line) in seen:
            continue
        seen.add((m.rule_id, m.line))
        out.append(m)
    return out


# -- JavaScript / TypeScript ---------------------------------------------------------


def _js_matches(root: Node, remap: Callable[[int], int], cf: ChangedFile) -> list[Match]:
    out: list[Match] = []
    imports_child_process = "child_process" in text(root)
    for n in walk(root):
        t = n.type
        ln = remap(line(n))
        if t == "call_expression":
            fn = n.child_by_field_name("function")
            callee = text(fn)
            prop = (
                text(fn.child_by_field_name("property"))
                if fn is not None and fn.type == "member_expression"
                else ""
            )
            obj = (
                text(fn.child_by_field_name("object"))
                if fn is not None and fn.type == "member_expression"
                else ""
            )
            args = n.child_by_field_name("arguments")
            first = args.named_children[0] if args is not None and args.named_children else None
            if callee == "eval":
                out.append(
                    Match(
                        "CG-SEC-001",
                        ln,
                        "`eval()` added",
                        f"`{_short(n)}` evaluates a string as code.",
                    )
                )
            elif (
                callee in ("setTimeout", "setInterval")
                and first is not None
                and first.type in ("string", "template_string")
            ):
                out.append(
                    Match(
                        "CG-SEC-001",
                        ln,
                        f"`{callee}` with a string argument",
                        f"`{_short(n)}` compiles a string as code.",
                    )
                )
            elif prop == "insertAdjacentHTML" or (
                obj == "document" and prop in ("write", "writeln")
            ):
                out.append(
                    Match(
                        "CG-SEC-002",
                        ln,
                        f"HTML written with `{prop}`",
                        f"`{_short(n)}` writes markup into the document.",
                    )
                )
            elif callee.rsplit(".", 1)[-1] in ("exec", "execSync") and (
                imports_child_process or "child_process" in callee
            ):
                if first is not None and (
                    _has_substitution(first) or first.type in ("binary_expression", "identifier")
                ):
                    out.append(
                        Match(
                            "CG-SEC-003",
                            ln,
                            "Shell command built from dynamic input",
                            f"`{_short(n)}` passes an interpolated string to a shell.",
                        )
                    )
            elif obj == "console" and prop in _CONSOLE_METHODS and not cf.is_test:
                out.append(
                    Match(
                        "CG-DBG-001",
                        ln,
                        f"`{callee}` added",
                        f"`{_short(n)}` writes to the console.",
                        Severity.LOW,
                    )
                )
            elif prop == "forEach":
                if args is not None and any(_is_async_fn(a) for a in args.named_children):
                    out.append(
                        Match(
                            "CG-CON-001",
                            ln,
                            "Async callback passed to `forEach`",
                            f"`{_short(n)}`: forEach does not await the callbacks.",
                        )
                    )
            elif cf.is_test and callee in _FOCUS:
                out.append(
                    Match(
                        "CG-TST-003",
                        ln,
                        f"Focused test `{callee}` committed",
                        f"`{_short(n)}` makes the runner skip every other test.",
                    )
                )
            elif cf.is_test and callee in _SKIP:
                out.append(
                    Match(
                        "CG-TST-002",
                        ln,
                        f"Test disabled with `{callee}`",
                        f"`{_short(n)}` is no longer executed.",
                    )
                )
        elif t == "new_expression":
            if text(n.child_by_field_name("constructor")) == "Function":
                out.append(
                    Match(
                        "CG-SEC-001",
                        ln,
                        "`new Function()` added",
                        f"`{_short(n)}` compiles a string as code.",
                    )
                )
        elif t == "assignment_expression":
            left = n.child_by_field_name("left")
            right = n.child_by_field_name("right")
            sink = (
                left is not None
                and left.type == "member_expression"
                and text(left.child_by_field_name("property")) in _HTML_SINK_PROPERTIES
            )
            static_markup = (
                right is None
                or right.type == "string"
                or (right.type == "template_string" and not _has_substitution(right))
            )
            if sink and not static_markup:
                prop = text(left.child_by_field_name("property")) if left is not None else ""
                out.append(
                    Match(
                        "CG-SEC-002",
                        ln,
                        f"Dynamic value assigned to `{prop}`",
                        f"`{_short(n)}` renders unescaped markup.",
                    )
                )
        elif t == "jsx_attribute":
            name = n.named_children[0] if n.named_children else None
            if name is not None and text(name) == "dangerouslySetInnerHTML":
                out.append(
                    Match(
                        "CG-SEC-002",
                        ln,
                        "`dangerouslySetInnerHTML` added",
                        f"`{_short(n)}` bypasses React's escaping.",
                    )
                )
        elif t == "debugger_statement":
            out.append(
                Match(
                    "CG-DBG-001",
                    ln,
                    "`debugger` statement added",
                    "Execution pauses when developer tools are open.",
                    Severity.MEDIUM,
                )
            )
        elif t == "catch_clause":
            body = n.child_by_field_name("body")
            if body is not None and not [c for c in body.named_children if c.type != "comment"]:
                out.append(
                    Match(
                        "CG-ERR-001",
                        ln,
                        "Empty `catch` block",
                        "Errors raised in the `try` block are discarded.",
                    )
                )
        elif t == "comment":
            comment = text(n)
            if "@ts-ignore" in comment or "@ts-nocheck" in comment:
                directive = "@ts-nocheck" if "@ts-nocheck" in comment else "@ts-ignore"
                out.append(
                    Match(
                        "CG-TYP-001",
                        ln,
                        f"`{directive}` added",
                        "Type errors on the next line are suppressed.",
                    )
                )
        elif t == "as_expression":
            target = n.named_children[-1] if n.named_children else None
            if target is not None and text(target) == "any":
                out.append(
                    Match(
                        "CG-TYP-001",
                        ln,
                        "Cast to `any` added",
                        f"`{_short(n)}` disables type checking for this value.",
                        Severity.LOW,
                        Confidence.MEDIUM,
                    )
                )
        elif t == "pair":
            key = text(n.child_by_field_name("key")).strip("'\"")
            value = text(n.child_by_field_name("value")).strip("'\"`")
            if key in ("origin", "Access-Control-Allow-Origin") and value == "*":
                out.append(
                    Match(
                        "CG-CFG-001",
                        ln,
                        "Wildcard CORS origin",
                        "Any website can make credentialed cross-origin requests to this API.",
                        confidence=Confidence.MEDIUM,
                    )
                )
    return out


def _has_substitution(node: Node) -> bool:
    return node.type == "template_string" and any(
        c.type == "template_substitution" for c in node.named_children
    )


def _is_async_fn(node: Node) -> bool:
    return node.type in ("arrow_function", "function_expression", "function") and any(
        c.type == "async" for c in node.children
    )


def _short(node: Node, limit: int = 90) -> str:
    snippet = " ".join(text(node).split())
    return snippet if len(snippet) <= limit else snippet[: limit - 1] + "…"


# -- Python ----------------------------------------------------------------------


def _python_matches(root: Node, remap: Callable[[int], int], cf: ChangedFile) -> list[Match]:
    out: list[Match] = []
    for n in walk(root):
        t = n.type
        ln = remap(line(n))
        if t == "decorator" and cf.is_test:
            body = text(n)[1:].strip()
            if _PY_SKIP_DECORATORS.match(body):
                out.append(
                    Match(
                        "CG-TST-002",
                        ln,
                        f"Test disabled with `@{body.split('(')[0]}`",
                        f"`@{_short(n, 80)[1:]}`",
                        Severity.MEDIUM if "xfail" not in body else Severity.LOW,
                    )
                )
        elif t == "call":
            callee = text(n.child_by_field_name("function"))
            if cf.is_test and callee == "pytest.skip":
                out.append(
                    Match(
                        "CG-TST-002",
                        ln,
                        "Test skipped with `pytest.skip()`",
                        f"`{_short(n)}` skips the test at runtime.",
                    )
                )
            elif callee in (
                "yaml.unsafe_load",
                "yaml.unsafe_load_all",
                "marshal.loads",
                "jsonpickle.decode",
            ):
                # Not covered by Ruff's S-rules; checked in both full-context and diff-only modes.
                out.append(
                    Match(
                        "CG-SEC-004",
                        ln,
                        f"`{callee}()` on possibly untrusted data",
                        f"`{_short(n)}` can construct arbitrary objects.",
                    )
                )
            elif _keyword_value(n, "verify") == "False" and cf.full_context:
                # Ruff S501 only matches module-level requests/httpx calls; this also covers
                # Session/Client methods (e.g. self.session.get(..., verify=False)).
                out.append(
                    Match(
                        "CG-SEC-005",
                        ln,
                        "TLS verification disabled",
                        f"`{_short(n)}` passes verify=False.",
                    )
                )
        elif t == "comment":
            body = text(n)
            if re.search(r"#\s*type:\s*ignore", body):
                out.append(
                    Match(
                        "CG-TYP-001",
                        ln,
                        "`# type: ignore` added",
                        "Type errors on this line are suppressed.",
                        Severity.LOW,
                        Confidence.MEDIUM,
                    )
                )
        elif t == "assignment":
            left = text(n.child_by_field_name("left"))
            right = text(n.child_by_field_name("right"))
            if left == "DEBUG" and right == "True" and not cf.is_test:
                out.append(
                    Match(
                        "CG-CFG-001",
                        ln,
                        "`DEBUG = True` added",
                        "Debug mode exposes stack traces and internals to users.",
                    )
                )
            elif left == "ALLOWED_HOSTS" and "'*'" in right.replace('"', "'"):
                out.append(
                    Match(
                        "CG-CFG-001",
                        ln,
                        "`ALLOWED_HOSTS` allows any host",
                        "Host-header attacks become possible.",
                        confidence=Confidence.MEDIUM,
                    )
                )
        elif t == "keyword_argument":
            name = text(n.child_by_field_name("name"))
            value = text(n.child_by_field_name("value")).replace('"', "'")
            if name in ("allow_origins", "origins") and value in ("['*']", "'*'"):
                out.append(
                    Match(
                        "CG-CFG-001",
                        ln,
                        "Wildcard CORS origin",
                        f"`{_short(n)}` lets any website call this API.",
                        confidence=Confidence.MEDIUM,
                    )
                )
    return out


_BLOCKING_IN_ASYNC = frozenset(
    {
        "time.sleep",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.request",
        "urllib.request.urlopen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_output",
    }
)


def _python_fragment_matches(
    root: Node, remap: Callable[[int], int], cf: ChangedFile
) -> list[Match]:
    """Subset of Ruff's checks, evaluated on diff hunks when complete files are unavailable."""
    out: list[Match] = []
    for n in walk(root):
        ln = remap(line(n))
        if n.type == "call":
            callee = text(n.child_by_field_name("function"))
            args = n.child_by_field_name("arguments")
            kwargs = {
                text(a.child_by_field_name("name")): text(a.child_by_field_name("value"))
                for a in (args.named_children if args else [])
                if a.type == "keyword_argument"
            }
            if callee in ("eval", "exec"):
                out.append(
                    Match(
                        "CG-SEC-001",
                        ln,
                        f"`{callee}()` added",
                        f"`{_short(n)}` executes a string as code.",
                    )
                )
            elif callee in ("pickle.loads", "pickle.load", "cPickle.loads") or (
                callee == "yaml.load" and "SafeLoader" not in kwargs.get("Loader", "")
            ):
                out.append(
                    Match(
                        "CG-SEC-004",
                        ln,
                        f"`{callee}()` on possibly untrusted data",
                        f"`{_short(n)}` can instantiate arbitrary objects.",
                    )
                )
            elif callee == "os.system" or (
                callee.startswith("subprocess.") and kwargs.get("shell") == "True"
            ):
                out.append(
                    Match(
                        "CG-SEC-003",
                        ln,
                        "Command executed through a shell",
                        f"`{_short(n)}` runs through a shell.",
                    )
                )
            elif kwargs.get("verify") == "False":
                out.append(
                    Match(
                        "CG-SEC-005",
                        ln,
                        "TLS verification disabled",
                        f"`{_short(n)}` passes verify=False.",
                    )
                )
            elif (
                callee.rsplit(".", 1)[-1] in ("execute", "executemany", "raw")
                and args is not None
                and args.named_children
                and _formatted_sql(args.named_children[0])
            ):
                out.append(
                    Match(
                        "CG-SEC-006",
                        ln,
                        "SQL built with string formatting",
                        f"`{_short(n)}` interpolates values into SQL.",
                    )
                )
            elif callee in ("breakpoint", "pdb.set_trace", "ipdb.set_trace"):
                out.append(
                    Match(
                        "CG-DBG-001",
                        ln,
                        f"`{callee}()` left in code",
                        "Execution pauses at this line.",
                        Severity.MEDIUM,
                    )
                )
            elif callee == "print" and not cf.is_test:
                out.append(
                    Match(
                        "CG-DBG-001",
                        ln,
                        "`print()` added",
                        f"`{_short(n)}` writes to stdout.",
                        Severity.LOW,
                        Confidence.MEDIUM,
                    )
                )
            elif callee in _BLOCKING_IN_ASYNC and _inside_async_def(n):
                out.append(
                    Match(
                        "CG-CON-002",
                        ln,
                        f"Blocking `{callee}` inside async function",
                        f"`{_short(n)}` blocks the event loop.",
                    )
                )
        elif n.type == "except_clause":
            has_type = any(c.is_named and c.type not in ("block", "comment") for c in n.children)
            body = next((c for c in n.children if c.type == "block"), None)
            only_pass = body is not None and [
                c.type for c in body.named_children if c.type != "comment"
            ] == ["pass_statement"]
            if not has_type or only_pass:
                what = "Bare `except:`" if not has_type else "`except ...: pass`"
                out.append(
                    Match(
                        "CG-ERR-001",
                        ln,
                        f"{what} added",
                        "Errors raised in the `try` block are discarded"
                        + (" (including KeyboardInterrupt/SystemExit)." if not has_type else "."),
                    )
                )
    return out


def _keyword_value(call: Node, name: str) -> str | None:
    args = call.child_by_field_name("arguments")
    for a in args.named_children if args is not None else []:
        if a.type == "keyword_argument" and text(a.child_by_field_name("name")) == name:
            return text(a.child_by_field_name("value"))
    return None


_SQL_KEYWORDS = re.compile(r"(?i)\b(select|insert|update|delete|where|values)\b")


def _formatted_sql(node: Node) -> bool:
    """f-strings, `%`/`+` formatting, or .format() applied to SQL text."""
    body = text(node)
    if not _SQL_KEYWORDS.search(body):
        return False
    if node.type == "string" and any(c.type == "interpolation" for c in node.named_children):
        return True
    if node.type == "binary_operator":
        return True
    return node.type == "call" and text(node.child_by_field_name("function")).endswith(".format")


def _inside_async_def(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "function_definition":
            return any(c.type == "async" for c in parent.children)
        parent = parent.parent
    return False


# -- reporting ---------------------------------------------------------------------

_FAILURE: dict[str, str] = {
    "CG-SEC-004": "A crafted payload executes code during deserialisation (pickle `__reduce__`, YAML object tags).",
    "CG-SEC-005": "An attacker on the network path can impersonate the server and read or alter the traffic.",
    "CG-CON-002": "Under load the event loop stalls for the duration of the blocking call, delaying every concurrent request.",
    "CG-SEC-006": "A value such as `1 OR 1=1` or `1; DROP TABLE users` changes the meaning of the query.",
    "CG-SEC-001": "If any part of the evaluated string is influenced by user input, an attacker can run arbitrary JavaScript with the page's or server's privileges.",
    "CG-SEC-002": "An attacker-controlled string (e.g. a user name containing `<img src=x onerror=...>`) executes script in other users' browsers.",
    "CG-SEC-003": "A crafted input such as `; rm -rf ~` is executed by the shell with the server's permissions.",
    "CG-DBG-001": "Debug output leaks internal data to logs or browser consoles in production.",
    "CG-ERR-001": "When the guarded call fails, execution continues with partial state and nobody is alerted.",
    "CG-CON-001": "Iterations run concurrently and the surrounding function returns before they finish; rejected promises become unhandled rejections.",
    "CG-TST-002": "The behaviour this test verified can regress without CI noticing.",
    "CG-TST-003": "CI runs only the focused test(s) in this file; regressions covered by the other tests go unnoticed.",
    "CG-TYP-001": "A type error the compiler would have reported reaches runtime instead.",
    "CG-CFG-001": "The deployed service is reachable or debuggable in ways production should not allow.",
}
_TESTS: dict[str, SuggestedTest] = {
    "CG-SEC-004": SuggestedTest(
        description="Deserialise with json or yaml.safe_load and add a test that a malicious payload is rejected.",
        kind="unit",
    ),
    "CG-SEC-005": SuggestedTest(
        description="Keep verify=True (or point it at a CA bundle) and add a test asserting the client is configured with verification enabled.",
        kind="unit",
    ),
    "CG-CON-002": SuggestedTest(
        description="Use the async equivalent (asyncio.sleep, httpx.AsyncClient, asyncio.create_subprocess_exec) and run the handler under asyncio debug mode in a test.",
        kind="integration",
    ),
    "CG-SEC-006": SuggestedTest(
        description='Pass values as query parameters and add a test with an injection payload such as "1 OR 1=1" that must match no rows.',
        kind="unit",
    ),
    "CG-SEC-001": SuggestedTest(
        description="Replace dynamic evaluation with explicit parsing (e.g. JSON.parse) and add a test passing a malicious string that must not execute.",
        kind="unit",
    ),
    "CG-SEC-002": SuggestedTest(
        description="Render with textContent or a sanitizer (DOMPurify) and add a test asserting `<img src=x onerror=alert(1)>` is rendered inert.",
        kind="unit",
    ),
    "CG-SEC-003": SuggestedTest(
        description="Use execFile/spawn with an argument array and add a test where the input contains `;` and `$(...)`.",
        kind="unit",
    ),
    "CG-DBG-001": SuggestedTest(
        description="Remove the statement; enforce `no-console`/`no-debugger` lint rules in CI.",
        kind="static",
    ),
    "CG-ERR-001": SuggestedTest(
        description="Add a test that makes the try block throw and asserts the error is logged or propagated.",
        kind="unit",
    ),
    "CG-CON-001": SuggestedTest(
        description="Use `for...of` with await or `await Promise.all(items.map(...))`; add a test asserting all work completes before the function resolves.",
        kind="unit",
    ),
    "CG-TST-002": SuggestedTest(
        description="Re-enable the test or delete it with a justification; track skipped tests in CI output.",
        kind="review",
    ),
    "CG-TST-003": SuggestedTest(
        description="Remove `.only`; enable a lint rule such as `no-only-tests` or `--forbid-only` in CI.",
        kind="static",
    ),
    "CG-TYP-001": SuggestedTest(
        description="Fix the underlying type error instead of suppressing it.", kind="static"
    ),
    "CG-CFG-001": SuggestedTest(
        description="Load these values from environment-specific configuration and add a test that production settings disable debug/wildcards.",
        kind="unit",
    ),
}


def _report(ctx: AnalysisContext, cf: ChangedFile, m: Match) -> None:
    ev = ctx.code_evidence(
        cf.path, m.line, m.line, title=f"{m.title} ({cf.path}:{m.line})", type=EvidenceType.PATTERN_MATCH,
        source="tree-sitter pattern rule", data={"rule": m.rule_id, "detail": m.detail}, context=2,
    )  # fmt: skip
    symbol = cf.head_index.innermost_symbol(m.line) if cf.head_index else None
    ctx.add_finding(
        m.rule_id,
        title=m.title,
        description=m.detail + (f" (in `{symbol.qualname}`)" if symbol else ""),
        location=Location(
            file=cf.path,
            start_line=m.line,
            end_line=m.line,
            symbol=symbol.qualname if symbol else None,
        ),
        evidence_ids=[ev],
        failure_scenario=_FAILURE[m.rule_id],
        suggested_test=_TESTS[m.rule_id],
        severity=m.severity,
        confidence=m.confidence,
        related_symbols=[symbol.qualname] if symbol else [],
        discriminator=m.title,
    )
