"""Line-level rules that apply to every text file in the change.

* secrets (provider-specific token formats + high-entropy assignments)
* committed environment files
* prompt-injection text aimed at AI reviewers
* destructive database migrations (SQL, Alembic, Django, Knex)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.secrets import find_secrets
from changeguard.analysis.workspace import ChangedFile
from changeguard.languages import language_for_path
from changeguard.report.models import Confidence, EvidenceType, Location, Severity, SuggestedTest

# -- prompt injection -----------------------------------------------------------------

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|any|preceding|your)\b.{0,30}\b(instructions?|prompts?|rules?|directives?|guidelines?)\b"),
    re.compile(r"(?i)\byou are (now )?(an? )?(ai|assistant|language model|llm|chatbot|code reviewer|security reviewer)\b"),
    re.compile(r"(?i)\b(system|developer)\s+(prompt|message|instructions?)\b"),
    re.compile(r"(?i)\b(do not|don't|never)\s+(report|flag|mention|warn about|raise|include)\b.{0,40}\b(issues?|findings?|vulnerabilit\w*|risks?|problems?|this|anything)\b"),
    re.compile(r"(?i)\b(mark|report|treat|classify|rate|label)\b.{0,30}\b(this|the)\b.{0,20}\b(change|code|pr|pull request|commit|diff|file|patch)\b.{0,20}\b(as )?(safe|approved|low[- ]risk|harmless|secure|benign|clean)\b"),
    re.compile(r"(?i)<\s*/?\s*(system|assistant|im_start|im_end|instructions?)\s*>"),
    re.compile(r"(?i)\b(ai|llm|copilot|claude|gpt|chatgpt|gemini|reviewer|changeguard)\b[^\n]{0,20}:\s*(ignore|approve|disregard|you must|always|never|respond)"),
)  # fmt: skip

# -- migrations -------------------------------------------------------------------------

_SQL_RULES: tuple[tuple[re.Pattern[str], str, Severity], ...] = (
    (re.compile(r"(?i)\bDROP\s+TABLE\b"), "DROP TABLE", Severity.CRITICAL),
    (re.compile(r"(?i)\bTRUNCATE\b(\s+TABLE)?\s+[\w.\"`]"), "TRUNCATE", Severity.CRITICAL),
    (re.compile(r"(?i)\bDROP\s+COLUMN\b|\bALTER\s+TABLE\s+[\w.\"`]+\s+DROP\s+(?!CONSTRAINT|INDEX|DEFAULT|NOT)"), "DROP COLUMN", Severity.HIGH),
    (re.compile(r"(?i)\bDELETE\s+FROM\s+[\w.\"`]+\s*(;|\"|'|$)"), "DELETE without WHERE", Severity.HIGH),
    (re.compile(r"(?i)\bRENAME\s+(COLUMN\b|TO\b)"), "RENAME", Severity.HIGH),
    (re.compile(r"(?i)\bALTER\s+COLUMN\b.*\b(TYPE|SET\s+DATA\s+TYPE)\b"), "column type change", Severity.MEDIUM),
    (re.compile(r"(?i)\bSET\s+NOT\s+NULL\b"), "SET NOT NULL", Severity.MEDIUM),
)  # fmt: skip
_FRAMEWORK_RULES: tuple[tuple[re.Pattern[str], str, Severity], ...] = (
    (re.compile(r"\bop\.drop_table\("), "op.drop_table", Severity.CRITICAL),
    (re.compile(r"\bop\.drop_column\("), "op.drop_column", Severity.HIGH),
    (re.compile(r"\bop\.rename_table\("), "op.rename_table", Severity.HIGH),
    (re.compile(r"\bop\.alter_column\(.*\bnew_column_name\s*="), "column rename (op.alter_column)", Severity.HIGH),
    (re.compile(r"\bop\.alter_column\(.*\b(type_\s*=|nullable\s*=\s*False)"), "op.alter_column", Severity.MEDIUM),
    (re.compile(r"\bmigrations\.DeleteModel\("), "migrations.DeleteModel", Severity.CRITICAL),
    (re.compile(r"\bmigrations\.RemoveField\("), "migrations.RemoveField", Severity.HIGH),
    (re.compile(r"\bmigrations\.Rename(Field|Model)\("), "migrations.Rename", Severity.HIGH),
    (re.compile(r"\bmigrations\.AlterField\("), "migrations.AlterField", Severity.MEDIUM),
    (re.compile(r"\.dropTable(IfExists)?\("), "knex dropTable", Severity.CRITICAL),
    (re.compile(r"\.dropColumns?\("), "knex dropColumn", Severity.HIGH),
    (re.compile(r"\.renameColumn\("), "knex renameColumn", Severity.HIGH),
)  # fmt: skip
_SQL_HINT = re.compile(r"(?i)\b(execute|executescript|raw|query|sql|op\.execute|RunSQL)\b")
_MIGRATION_DIRS = ("migrations", "migration", "alembic", "migrate", "db/versions", "schema")
_COLUMN_STOPWORDS = frozenset(
    {"id", "name", "type", "data", "value", "key", "status", "created", "updated", "user"}
)
_ENV_SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".defaults")


@dataclass(slots=True)
class _MigrationHit:
    line: int
    operation: str
    severity: Severity
    column: str | None


def analyze_textual(ctx: AnalysisContext) -> dict[str, int]:
    stats = {"secrets": 0, "prompt_injection": 0, "migrations": 0, "env_files": 0}
    injection_lines: set[tuple[str, int]] = set()
    for cf in ctx.files:
        if cf.diff.is_binary:
            continue
        added = [
            (ln.new_lineno, ln.content)
            for h in cf.diff.hunks
            for ln in h.lines
            if ln.kind == "add" and ln.new_lineno
        ]
        if not added:
            continue
        stats["secrets"] += _secrets(ctx, cf, added)
        stats["env_files"] += _env_file(ctx, cf, added)
        hits = _prompt_injection(ctx, cf, added)
        injection_lines |= {(cf.path, n) for n in hits}
        stats["prompt_injection"] += len(hits) and 1
        stats["migrations"] += _migrations(ctx, cf, added)
    ctx.stage_data["injection_lines"] = injection_lines
    return stats


def _secrets(ctx: AnalysisContext, cf: ChangedFile, added: list[tuple[int, str]]) -> int:
    count = 0
    for number, content in added:
        for match in find_secrets(content):
            provider = match.provider_specific
            if cf.is_test and not provider:
                severity, confidence = Severity.MEDIUM, Confidence.LOW
            else:
                severity = Severity.CRITICAL if provider else Severity.HIGH
                confidence = Confidence.HIGH if provider else Confidence.MEDIUM
            ev = ctx.code_evidence(
                cf.path, number, number, title=f"{match.kind} at {cf.path}:{number}", type=EvidenceType.PATTERN_MATCH,
                source="secret scanner", data={"detector": match.kind, "masked": match.masked}, context=1,
            )  # fmt: skip
            ctx.add_finding(
                "CG-SEC-010",
                title=f"{match.kind} committed",
                description=f"Line {number} adds what looks like a {match.kind.lower()} (`{match.masked}`). The value is "
                "masked in this report and is never sent to an AI provider.",
                location=Location(file=cf.path, start_line=number, end_line=number),
                evidence_ids=[ev],
                failure_scenario="Anyone with read access to the repository or its history (forks, CI logs, "
                "leaked clones) can use the credential until it is rotated.",
                suggested_test=SuggestedTest(
                    description="Rotate the credential now, load it from a secret manager or environment variable, and "
                    "add a pre-commit secret scanner (e.g. gitleaks) to CI.",
                    kind="review",
                ),
                severity=severity,
                confidence=confidence,
                tags=["secret"],
                discriminator=f"{match.start}",
            )
            count += 1
    return count


def _env_file(ctx: AnalysisContext, cf: ChangedFile, added: list[tuple[int, str]]) -> int:
    name = PurePosixPath(cf.path).name
    if not (name == ".env" or name.startswith(".env.")) or name.endswith(_ENV_SAFE_SUFFIXES):
        return 0
    assignments = [
        (n, c) for n, c in added if re.match(r"^\s*(export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S", c)
    ]
    if not assignments:
        return 0
    first, last = assignments[0][0], assignments[-1][0]
    ev = ctx.code_evidence(
        cf.path,
        first,
        min(last, first + 10),
        title=f"Environment file {cf.path}",
        type=EvidenceType.PATTERN_MATCH,
        source="secret scanner",
        context=0,
    )
    ctx.add_finding(
        "CG-SEC-011",
        title=f"Environment file `{name}` committed",
        description=f"{len(assignments)} non-empty variable assignment(s) added to {cf.path}.",
        location=Location(file=cf.path, start_line=first, end_line=last),
        evidence_ids=[ev],
        failure_scenario="Deployment secrets in the file become readable by everyone with repository access.",
        suggested_test=SuggestedTest(
            description="Remove the file from version control, add it to .gitignore, and commit a `.env.example` "
            "with placeholder values instead.",
            kind="review",
        ),
        tags=["secret", "config"],
    )
    return 1


def _prompt_injection(
    ctx: AnalysisContext, cf: ChangedFile, added: list[tuple[int, str]]
) -> list[int]:
    hits: list[tuple[int, str]] = []
    for number, content in added:
        for pattern in INJECTION_PATTERNS:
            m = pattern.search(content)
            if m:
                hits.append((number, m.group(0)))
                break
    if not hits:
        return []
    first = hits[0][0]
    evidence = [
        ctx.code_evidence(cf.path, n, n, title=f"Instruction-like text at {cf.path}:{n}", type=EvidenceType.PATTERN_MATCH,
                          source="prompt-injection detector", data={"matched": phrase[:120]}, context=1)
        for n, phrase in hits[:5]
    ]  # fmt: skip
    ctx.add_finding(
        "CG-AIS-001",
        title=f"Text addressed to AI reviewers added in {cf.path}",
        description=f"{len(hits)} added line(s) contain instruction-like text aimed at automated reviewers "
        f"(e.g. “{hits[0][1][:80]}”). These lines are withheld from the AI model.",
        location=Location(file=cf.path, start_line=first, end_line=hits[-1][0]),
        evidence_ids=evidence,
        failure_scenario="An AI-assisted review that reads these lines verbatim could be steered into approving the "
        "change or omitting real issues.",
        suggested_test=SuggestedTest(
            description="Remove the text, and review the surrounding change manually: it may be hiding a real issue.",
            kind="review",
        ),
        tags=["ai-safety"],
    )
    return [n for n, _ in hits]


def _is_migration_path(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(".sql") or any(f"/{d}/" in f"/{lowered}" for d in _MIGRATION_DIRS)


def _migrations(ctx: AnalysisContext, cf: ChangedFile, added: list[tuple[int, str]]) -> int:
    migration_file = _is_migration_path(cf.path)
    hits: list[_MigrationHit] = []
    for number, content in added:
        stripped = content.strip()
        if stripped.startswith(("--", "#", "//")):
            continue
        rules = list(_FRAMEWORK_RULES)
        if migration_file or _SQL_HINT.search(content):
            rules += list(_SQL_RULES)
        for pattern, operation, severity in rules:
            if pattern.search(content):
                hits.append(
                    _MigrationHit(number, operation, severity, _column_name(content, operation))
                )
                break
    for hit in hits:
        ev = ctx.code_evidence(
            cf.path, hit.line, hit.line, title=f"{hit.operation} at {cf.path}:{hit.line}", type=EvidenceType.PATTERN_MATCH,
            source="migration rules", data={"operation": hit.operation, "column": hit.column}, context=2,
        )  # fmt: skip
        ctx.add_finding(
            "CG-MIG-001",
            title=f"Destructive migration: {hit.operation}",
            description=f"{cf.path}:{hit.line} performs `{hit.operation}`"
            + (f" on column `{hit.column}`." if hit.column else "."),
            location=Location(file=cf.path, start_line=hit.line, end_line=hit.line),
            evidence_ids=[ev],
            failure_scenario="During a rolling deploy, instances still running the previous code read or write the "
            "dropped/renamed structure and fail; the data removed cannot be recovered without a backup.",
            suggested_test=SuggestedTest(
                description="Run the migration (upgrade and downgrade) against a production-sized snapshot in staging; "
                "use expand/contract: stop reading the column in one release and drop it in a later one.",
                kind="integration",
            ),
            severity=hit.severity,
            confidence=Confidence.HIGH,
            tags=["migration"],
            discriminator=hit.operation,
        )
        if hit.column:
            _column_references(ctx, cf, hit, ev)
    return len(hits)


def _column_name(content: str, operation: str) -> str | None:
    patterns = (
        r"\bop\.drop_column\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([A-Za-z_][\w]*)['\"]",
        r"\bop\.alter_column\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([A-Za-z_][\w]*)['\"].*new_column_name",
        r"(?i)\bDROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?[\"`]?([A-Za-z_][\w]*)",
        r"(?i)\bRENAME\s+COLUMN\s+[\"`]?([A-Za-z_][\w]*)",
        r"\bmigrations\.(?:RemoveField|RenameField)\(.*?\bname\s*=\s*['\"]([A-Za-z_][\w]*)['\"]",
        r"\bmigrations\.RenameField\(.*?\bold_name\s*=\s*['\"]([A-Za-z_][\w]*)['\"]",
        r"\.dropColumn\(\s*['\"]([A-Za-z_][\w]*)['\"]",
        r"\.renameColumn\(\s*['\"]([A-Za-z_][\w]*)['\"]",
    )
    for p in patterns:
        m = re.search(p, content)
        if m:
            return m.group(1)
    return None


def _column_references(
    ctx: AnalysisContext, cf: ChangedFile, hit: _MigrationHit, migration_ev: str | None
) -> None:
    column = hit.column
    if not column or column.lower() in _COLUMN_STOPWORDS or len(column) < 4 or not ctx.full_context:
        return
    pattern = re.compile(rf"\b{re.escape(column)}\b")
    refs: list[tuple[str, int]] = []
    for path, text in sorted(ctx.workspace.head_repo.items()):
        if path == cf.path or _is_migration_path(path) or language_for_path(path) is None:
            continue
        for i, line_text in enumerate(text.split("\n"), start=1):
            if pattern.search(line_text):
                refs.append((path, i))
                if len(refs) >= 20:
                    break
    if not refs:
        return
    evidence = [migration_ev] + [
        ctx.code_evidence(p, n, n, title=f"`{column}` referenced at {p}:{n}", type=EvidenceType.SYMBOL_REFERENCE,
                          source="repository snapshot (text search)", context=1)
        for p, n in refs[:6]
    ]  # fmt: skip
    ctx.add_finding(
        "CG-MIG-002",
        title=f"Column `{column}` is dropped/renamed but still referenced in code",
        description=f"The migration removes or renames `{column}`, but {len(refs)} line(s) in "
        f"{len({p for p, _ in refs})} source file(s) still mention it.",
        location=Location(file=cf.path, start_line=hit.line, end_line=hit.line),
        evidence_ids=evidence,
        failure_scenario=f"Queries that select or write `{column}` fail (e.g. 'column does not exist') as soon as the "
        f"migration runs, starting with {refs[0][0]}:{refs[0][1]}.",
        suggested_test=SuggestedTest(
            description="Remove the code references first (or in the same deploy before the migration), then run "
            "the integration suite against the migrated schema.",
            kind="integration",
        ),
        confidence=Confidence.MEDIUM,
        tags=["migration"],
        discriminator=column,
    )
