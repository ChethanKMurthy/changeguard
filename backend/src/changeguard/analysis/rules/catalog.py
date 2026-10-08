"""Catalog of every rule ChangeGuard can emit.

Each rule declares its provenance (``kind``): *deterministic* rules report a
fact established by analysis (a call site that no longer type-checks against
the new signature, a measured uncovered line, a matched secret pattern);
*heuristic* rules report an inferred risk whose impact depends on context
(no test references a changed function, an operator flipped in a condition).
"""

from __future__ import annotations

from dataclasses import dataclass

from changeguard.report.models import Category, FindingKind, Severity


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    title: str
    category: Category
    kind: FindingKind
    severity: Severity
    rationale: str
    languages: tuple[str, ...] = ()


D, H = FindingKind.DETERMINISTIC, FindingKind.HEURISTIC
S = Severity
C = Category

_RULES: list[Rule] = [
    # -- API contract ----------------------------------------------------------
    Rule("CG-API-001", "Call site incompatible with new signature", C.BREAKING_CHANGE, D, S.HIGH,
         "A caller still uses the old calling convention. In Python this raises TypeError at call time; in "
         "TypeScript it fails compilation.", ("python", "javascript", "typescript")),
    Rule("CG-API-002", "Removed symbol is still referenced", C.BREAKING_CHANGE, D, S.CRITICAL,
         "Code that imports or calls a removed or renamed symbol fails at import or call time.",
         ("python", "javascript", "typescript")),
    Rule("CG-API-003", "Breaking signature change", C.BREAKING_CHANGE, H, S.MEDIUM,
         "The signature changed incompatibly. No incompatible caller was found in the analysed code, but callers "
         "outside it (other services, packages, scripts) would break.", ("python", "javascript", "typescript")),
    Rule("CG-API-004", "Function became async but callers do not await it", C.BREAKING_CHANGE, D, S.HIGH,
         "Calling an async function without awaiting it returns a coroutine/promise instead of the value, "
         "silently changing behaviour.", ("python", "javascript", "typescript")),
    Rule("CG-API-005", "Default argument value changed", C.BEHAVIOR_CHANGE, H, S.MEDIUM,
         "Callers that omit the argument now receive different behaviour without any code change on their side.",
         ("python", "javascript", "typescript")),
    Rule("CG-API-006", "Return type annotation changed", C.BEHAVIOR_CHANGE, H, S.LOW,
         "Callers may depend on the previous return type.", ("python", "typescript")),
    Rule("CG-API-007", "Public symbol removed", C.BREAKING_CHANGE, H, S.LOW,
         "A public symbol was removed. No internal references remain, but external consumers may rely on it.",
         ("python", "javascript", "typescript")),
    # -- Syntax ----------------------------------------------------------------
    Rule("CG-SYN-001", "Syntax error introduced", C.SYNTAX_ERROR, D, S.CRITICAL,
         "The changed file no longer parses. It will fail at import/compile time.",
         ("python", "javascript", "typescript")),
    # -- JS/TS patterns --------------------------------------------------------
    Rule("CG-SEC-001", "Dynamic code execution", C.SECURITY, D, S.HIGH,
         "eval/exec/new Function execute strings as code; attacker-influenced input leads to code injection.",
         ("javascript", "typescript", "python")),
    Rule("CG-SEC-002", "Unsafe HTML sink", C.SECURITY, D, S.HIGH,
         "Assigning untrusted strings to HTML sinks enables cross-site scripting.", ("javascript", "typescript")),
    Rule("CG-SEC-003", "Shell command built from dynamic input", C.SECURITY, D, S.HIGH,
         "Passing data to a shell enables command injection.", ("javascript", "typescript", "python")),
    Rule("CG-SEC-004", "Unsafe deserialisation", C.SECURITY, D, S.HIGH,
         "pickle and yaml.load can construct arbitrary objects (and run code) from untrusted data.", ("python",)),
    Rule("CG-SEC-005", "TLS certificate verification disabled", C.SECURITY, D, S.HIGH,
         "Disabling certificate checks allows man-in-the-middle interception.", ("python",)),
    Rule("CG-SEC-006", "SQL built from string formatting", C.SECURITY, D, S.HIGH,
         "Interpolating values into SQL text enables SQL injection; use parameterised queries.", ("python",)),
    Rule("CG-SEC-010", "Hard-coded secret", C.SECRET_EXPOSURE, D, S.CRITICAL,
         "Credentials committed to source control are exposed to everyone with repository access and persist in "
         "history after removal; they must be rotated."),
    Rule("CG-SEC-011", "Environment file committed", C.SECRET_EXPOSURE, D, S.MEDIUM,
         "Environment files usually hold deployment secrets and should not be committed."),
    Rule("CG-ERR-001", "Exception silently swallowed", C.ERROR_HANDLING, D, S.MEDIUM,
         "An empty or bare handler hides failures, turning errors into silent data corruption or missing work.",
         ("javascript", "typescript", "python")),
    Rule("CG-ERR-002", "Error handling removed", C.ERROR_HANDLING, H, S.MEDIUM,
         "A try/except (try/catch) block was removed from a modified function; failures that were handled now "
         "propagate to callers.", ("python", "javascript", "typescript")),
    Rule("CG-CON-001", "Async callback passed to forEach", C.CONCURRENCY, D, S.MEDIUM,
         "Array.prototype.forEach ignores returned promises: iterations run concurrently and errors are "
         "unhandled.", ("javascript", "typescript")),
    Rule("CG-CON-002", "Blocking call inside async function", C.CONCURRENCY, D, S.MEDIUM,
         "A blocking call inside a coroutine stalls the event loop and every concurrent request.", ("python",)),
    Rule("CG-DBG-001", "Debug artifact left in code", C.DEBUG_ARTIFACT, D, S.LOW,
         "Debug statements leak data to logs or pause execution in production.", ("javascript", "typescript", "python")),
    Rule("CG-TYP-001", "Type checking suppressed", C.TYPE_SAFETY, D, S.LOW,
         "Suppressing the type checker hides the class of errors the compiler would otherwise catch.",
         ("typescript", "python")),
    Rule("CG-CFG-001", "Risky configuration value", C.CONFIGURATION, H, S.MEDIUM,
         "Debug mode or wildcard CORS in application configuration weakens production security."),
    # -- Tests -----------------------------------------------------------------
    Rule("CG-TST-001", "No related tests found for changed code", C.TEST_GAP, H, S.MEDIUM,
         "No test in the snapshot imports and references the changed symbol, so a regression may go undetected. "
         "Tests that exercise it indirectly are not detected."),
    Rule("CG-TST-002", "Test disabled", C.TEST_INTEGRITY, D, S.MEDIUM,
         "A skip marker removes the test from the suite; the behaviour it covered is no longer verified."),
    Rule("CG-TST-003", "Focused test committed", C.TEST_INTEGRITY, D, S.HIGH,
         ".only restricts the runner to the focused test(s); every other test in the file stops running in CI.",
         ("javascript", "typescript")),
    Rule("CG-TST-004", "Assertions removed from test", C.TEST_INTEGRITY, D, S.MEDIUM,
         "Fewer assertions means the test verifies less behaviour than before."),
    Rule("CG-TST-005", "Tests deleted", C.TEST_INTEGRITY, D, S.MEDIUM,
         "Deleted tests reduce regression protection; confirm the behaviour they covered is gone or re-tested."),
    # -- Coverage --------------------------------------------------------------
    Rule("CG-COV-001", "Changed lines not covered by tests", C.COVERAGE_GAP, D, S.MEDIUM,
         "The uploaded coverage report marks these changed executable lines as never executed by the test suite."),
    Rule("CG-COV-002", "Changed file absent from coverage report", C.COVERAGE_GAP, H, S.LOW,
         "The coverage report has no data for this changed source file; it may not be imported by any test."),
    # -- Data / dependencies ---------------------------------------------------
    Rule("CG-MIG-001", "Destructive schema migration", C.DATA_MIGRATION, D, S.HIGH,
         "Dropping or rewriting tables/columns destroys data and breaks code still reading it during a rolling "
         "deploy."),
    Rule("CG-MIG-002", "Dropped column still referenced in code", C.DATA_MIGRATION, H, S.HIGH,
         "Application code still references a column this migration removes or renames."),
    Rule("CG-DEP-001", "Major version change of a dependency", C.DEPENDENCY, H, S.MEDIUM,
         "Major releases commonly contain breaking API changes."),
    Rule("CG-DEP-002", "New dependency added", C.DEPENDENCY, H, S.LOW,
         "New third-party code enters the supply chain and should be reviewed for maintenance and licence."),
    Rule("CG-DEP-003", "Dependency removed", C.DEPENDENCY, H, S.MEDIUM,
         "Code that still imports a removed dependency fails at import time."),
    Rule("CG-DEP-004", "Version constraint loosened", C.DEPENDENCY, H, S.LOW,
         "A looser constraint lets future installs pull untested versions."),
    # -- Logic / metrics -------------------------------------------------------
    Rule("CG-LOG-001", "Condition logic changed", C.LOGIC_CHANGE, H, S.MEDIUM,
         "A comparison/boolean operator or negation changed. Boundary behaviour differs, which is a classic "
         "source of off-by-one and inverted-condition bugs."),
    Rule("CG-LOG-002", "Boundary constant changed", C.LOGIC_CHANGE, H, S.LOW,
         "A numeric constant in a condition changed, moving a threshold."),
    Rule("CG-CPX-001", "Complexity increased", C.COMPLEXITY, H, S.LOW,
         "Higher cyclomatic complexity means more paths to test and more room for untested edge cases.",
         ("python", "javascript", "typescript")),
    # -- AI-specific security ------------------------------------------------
    Rule("CG-AIS-001", "Prompt-injection text in change", C.PROMPT_INJECTION, D, S.MEDIUM,
         "Text addressed to AI reviewers attempts to manipulate automated review. ChangeGuard neutralises it "
         "before any model sees the code, and AI output cannot remove deterministic findings."),
]  # fmt: skip

RULES: dict[str, Rule] = {r.id: r for r in _RULES}

# Ruff codes ChangeGuard runs differentially (only diagnostics *introduced* by the
# change are reported), with the category and severity we assign to each.
RUFF_RULES: dict[str, tuple[Category, Severity, str]] = {
    "invalid-syntax": (C.SYNTAX_ERROR, S.CRITICAL, "The file no longer parses."),
    "F821": (C.CORRECTNESS, S.HIGH, "Undefined name: raises NameError when the line executes."),
    "F823": (
        C.CORRECTNESS,
        S.HIGH,
        "Local variable referenced before assignment: raises UnboundLocalError.",
    ),
    "F811": (
        C.CORRECTNESS,
        S.MEDIUM,
        "Redefinition of an unused name shadows the earlier definition.",
    ),
    "F632": (
        C.CORRECTNESS,
        S.MEDIUM,
        "`is` comparison with a literal depends on interning; use ==.",
    ),
    "F601": (
        C.CORRECTNESS,
        S.MEDIUM,
        "Dictionary key repeated; the earlier value is silently discarded.",
    ),
    "F704": (C.CORRECTNESS, S.HIGH, "yield outside a function is a SyntaxError."),
    "F706": (C.CORRECTNESS, S.HIGH, "return outside a function is a SyntaxError."),
    "F822": (C.CORRECTNESS, S.MEDIUM, "Name listed in __all__ is not defined."),
    "B006": (C.CORRECTNESS, S.MEDIUM, "Mutable default argument is shared between calls."),
    "B008": (
        C.CORRECTNESS,
        S.LOW,
        "Function call in default argument runs once at definition time.",
    ),
    "B012": (
        C.ERROR_HANDLING,
        S.HIGH,
        "return/break/continue in finally swallows in-flight exceptions.",
    ),
    "B015": (
        C.CORRECTNESS,
        S.MEDIUM,
        "Comparison result is discarded; this was probably meant to be an assert.",
    ),
    "B018": (C.CORRECTNESS, S.LOW, "Useless expression has no effect."),
    "B020": (C.CORRECTNESS, S.MEDIUM, "Loop variable overrides the iterable it iterates."),
    "B023": (
        C.CORRECTNESS,
        S.MEDIUM,
        "Closure captures the loop variable by reference (late binding).",
    ),
    "B904": (
        C.ERROR_HANDLING,
        S.LOW,
        "Exception re-raised without `from`, losing the original cause.",
    ),
    "B011": (C.CORRECTNESS, S.LOW, "`assert False` is removed under python -O."),
    "E722": (
        C.ERROR_HANDLING,
        S.MEDIUM,
        "Bare except also catches SystemExit and KeyboardInterrupt.",
    ),
    "BLE001": (C.ERROR_HANDLING, S.LOW, "Blind `except Exception` hides unexpected failures."),
    "S110": (C.ERROR_HANDLING, S.MEDIUM, "try/except/pass silently swallows errors."),
    "S102": (C.SECURITY, S.HIGH, "exec() runs arbitrary code."),
    "S307": (C.SECURITY, S.HIGH, "eval() runs arbitrary code; use ast.literal_eval for literals."),
    "S301": (
        C.SECURITY,
        S.HIGH,
        "pickle deserialisation of untrusted data executes arbitrary code.",
    ),
    "S506": (C.SECURITY, S.HIGH, "yaml.load without SafeLoader can instantiate arbitrary objects."),
    "S602": (C.SECURITY, S.HIGH, "subprocess with shell=True enables command injection."),
    "S604": (C.SECURITY, S.HIGH, "Function call with shell=True enables command injection."),
    "S605": (C.SECURITY, S.HIGH, "Starting a process with a shell enables command injection."),
    "S608": (C.SECURITY, S.HIGH, "SQL built with string formatting enables SQL injection."),
    "S105": (C.SECRET_EXPOSURE, S.MEDIUM, "Hard-coded password string."),
    "S106": (C.SECRET_EXPOSURE, S.MEDIUM, "Hard-coded password passed as an argument."),
    "S107": (C.SECRET_EXPOSURE, S.MEDIUM, "Hard-coded password default argument."),
    "S501": (C.SECURITY, S.HIGH, "TLS certificate verification disabled (verify=False)."),
    "S323": (C.SECURITY, S.HIGH, "Unverified SSL context disables certificate checks."),
    "S324": (C.SECURITY, S.MEDIUM, "Insecure hash function (MD5/SHA1) used."),
    "S311": (C.SECURITY, S.LOW, "Non-cryptographic random generator used."),
    "S113": (C.CORRECTNESS, S.LOW, "HTTP request without a timeout can hang indefinitely."),
    "S201": (C.SECURITY, S.HIGH, "Flask debug mode exposes an interactive debugger."),
    "S701": (C.SECURITY, S.HIGH, "Jinja2 autoescape disabled enables XSS."),
    "S103": (C.SECURITY, S.MEDIUM, "Overly permissive file permissions."),
    "S202": (C.SECURITY, S.MEDIUM, "tarfile.extractall without filtering allows path traversal."),
    "S104": (C.CONFIGURATION, S.LOW, "Binding to all interfaces exposes the service."),
    "ASYNC210": (
        C.CONCURRENCY,
        S.MEDIUM,
        "Blocking HTTP call inside async function stalls the event loop.",
    ),
    "ASYNC220": (C.CONCURRENCY, S.MEDIUM, "Blocking subprocess call inside async function."),
    "ASYNC221": (C.CONCURRENCY, S.MEDIUM, "Blocking subprocess call inside async function."),
    "ASYNC230": (C.CONCURRENCY, S.LOW, "Blocking file I/O inside async function."),
    "ASYNC251": (
        C.CONCURRENCY,
        S.MEDIUM,
        "time.sleep inside async function blocks the event loop.",
    ),
    "RUF006": (
        C.CONCURRENCY,
        S.MEDIUM,
        "Task created without keeping a reference may be garbage-collected.",
    ),
    "T100": (C.DEBUG_ARTIFACT, S.MEDIUM, "Debugger breakpoint left in code pauses execution."),
    "T201": (C.DEBUG_ARTIFACT, S.LOW, "print() left in non-test code."),
    "PLE1142": (C.CORRECTNESS, S.HIGH, "await outside async function is a SyntaxError."),
}

RUFF_SELECT = ",".join(code for code in RUFF_RULES if code != "invalid-syntax")


def ruff_rule_id(code: str) -> str:
    return f"RUFF-{code}"


def describe_rule(rule_id: str) -> dict[str, object] | None:
    """Rule metadata for API/UI consumption (ChangeGuard rules and ruff-derived rules)."""
    if rule_id in RULES:
        r = RULES[rule_id]
        return {
            "id": r.id,
            "title": r.title,
            "category": r.category.value,
            "kind": r.kind.value,
            "default_severity": r.severity.value,
            "rationale": r.rationale,
            "languages": list(r.languages),
            "source": "changeguard",
        }
    if rule_id.startswith("RUFF-"):
        code = rule_id[len("RUFF-") :]
        if code in RUFF_RULES:
            category, severity, rationale = RUFF_RULES[code]
            return {
                "id": rule_id,
                "title": f"Ruff {code}",
                "category": category.value,
                "kind": FindingKind.DETERMINISTIC.value,
                "default_severity": severity.value,
                "rationale": rationale,
                "languages": ["python"],
                "source": "ruff",
            }
    return None


def all_rules() -> list[dict[str, object]]:
    out = [describe_rule(r.id) for r in _RULES]
    out += [describe_rule(ruff_rule_id(code)) for code in RUFF_RULES]
    return [r for r in out if r is not None]
