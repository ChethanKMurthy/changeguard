from __future__ import annotations

import json
import subprocess
from pathlib import Path

from changeguard.ai.providers.base import GenerationRequest, GenerationResult, ProviderHealth
from changeguard.cli import main as cli_main
from changeguard.evaluation.dataset import Case, Label
from changeguard.evaluation.llm_review import LLMReviewBaseline, parse_findings
from changeguard.evaluation.matching import Prediction, match_case
from changeguard.evaluation.metrics import Counts, bootstrap, micro
from changeguard.evaluation.reporting import compare_to_baseline
from changeguard.report.exporters import _fence, _md, to_markdown, to_sarif
from tests.conftest import ChangeRunner, write_tree


def _p(pid: str, category: str, file: str, line: int) -> Prediction:
    return Prediction(pid, "R", category, "deterministic", "high", "high", file, line, line, pid)


def _case(labels: list[Label], negative: bool = False) -> Case:
    return Case(
        id="c",
        title="t",
        split="dev",
        language="python",
        description="d",
        expected=labels,
        negative=negative,
    )


def test_matching_is_one_to_one_with_tolerance() -> None:
    labels = [
        Label(id="L1", category="security", file="a.py", lines=(10, 10)),
        Label(id="L2", category="security", file="a.py", lines=(12, 12)),
    ]
    preds = [
        _p("P1", "security", "a.py", 11),
        _p("P2", "security", "a.py", 13),
        _p("P3", "security", "a.py", 40),
    ]
    result = match_case(_case(labels), preds)
    assert sorted(label for label, _ in result.true_positives) == ["L1", "L2"]
    assert [p.id for p in result.false_positives] == ["P3"]
    assert result.false_negatives == []


def test_duplicate_predictions_are_not_double_counted() -> None:
    labels = [Label(id="L1", category="security", file="a.py", lines=(10, 10))]
    result = match_case(
        _case(labels), [_p("P1", "security", "a.py", 10), _p("P2", "security", "a.py", 10)]
    )
    assert (
        len(result.true_positives) == 1
        and result.false_positives == []
        and len(result.acceptable) == 1
    )


def test_category_must_match() -> None:
    labels = [Label(id="L1", category="security", file="a.py", lines=(10, 10))]
    result = match_case(_case(labels), [_p("P1", "logic_change", "a.py", 10)])
    assert (
        result.true_positives == []
        and len(result.false_positives) == 1
        and len(result.false_negatives) == 1
    )


def test_metrics_and_bootstrap_are_deterministic() -> None:
    labels = [Label(id="L1", category="security", file="a.py", lines=(1, 1))]
    results = [
        match_case(_case(labels), [_p("P", "security", "a.py", 1)]),
        match_case(_case(labels), []),
    ]
    counts = micro(results)
    assert (counts.tp, counts.fp, counts.fn) == (1, 0, 1)
    assert counts.precision == 1.0 and counts.recall == 0.5
    assert (
        bootstrap(results, samples=200, seed=1)["recall"].as_list()
        == bootstrap(results, samples=200, seed=1)["recall"].as_list()
    )
    assert Counts().precision is None


def test_regression_gate_detects_lost_labels() -> None:
    def data(matched: list[str], precision: float) -> dict:  # type: ignore[type-arg]
        return {
            "systems": [{"system": "changeguard", "overall": {"precision": precision, "recall": 1.0, "f1": 1.0},
                         "negative_controls": {"false_positive_rate": 0.0}, "evidence": {"unsupported_findings": 0}}],
            "cases": {"changeguard": [{"case": "c1", "matched": matched, "false_positives": []}]},
        }  # fmt: skip

    assert compare_to_baseline(data(["L1"], 1.0), data(["L1"], 1.0)).passed
    result = compare_to_baseline(data([], 0.5), data(["L1"], 1.0))
    assert not result.passed
    assert any("no longer finds L1" in m for m in result.messages) and any(
        "precision dropped" in m for m in result.messages
    )


def test_markdown_escaping_and_fences() -> None:
    assert (
        _md("<script>alert(1)</script> and `<code>`")
        == "&lt;script&gt;alert(1)&lt;/script&gt; and `<code>`"
    )
    fenced = _fence("```\nnested\n```")
    assert fenced.startswith("````") and fenced.endswith("````")


def test_markdown_and_sarif_exports(run_change: ChangeRunner) -> None:
    base = {"src/a.py": "def f(x):\n    return x\n", "src/b.py": "from a import f\n\nf(1, 2)\n"}
    head = {"src/a.py": "def f(x):\n    return eval(x)\n"}
    report = run_change(base, head)
    md = to_markdown(report)
    assert "# ChangeGuard report" in md and "Review priority" in md and "S307" in md
    sarif = to_sarif(report)
    run = sarif["runs"][0]
    assert sarif["version"] == "2.1.0" and run["tool"]["driver"]["name"] == "ChangeGuard"
    rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
    for result in run["results"]:
        assert result["ruleId"] in rule_ids
        assert result["level"] in ("error", "warning", "note")
        region = result["locations"][0]["physicalLocation"].get("region")
        assert region is None or region["startLine"] >= 1


def test_schema_migration_keeps_existing_analyses(tmp_path: Path) -> None:
    import sqlite3

    from changeguard.storage.db import MIGRATIONS, AnalysisStore, Database, _split_sql

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for statement in _split_sql(MIGRATIONS[0]):
        conn.execute(statement)
    conn.execute("PRAGMA user_version = 1")
    conn.execute(
        "INSERT INTO analyses (id, created_at, updated_at, status, title, source, patch_sha256, options_json)"
        " VALUES ('an_00000000000000000001', 't', 't', 'queued', 'old', 'paste', 'x', '{}')"
    )
    conn.commit()
    conn.close()

    store = AnalysisStore(Database(path))
    row = store.get("an_00000000000000000001")
    assert row is not None and row.title == "old"
    assert store.get("an_00000000000000000001", workspace="w" * 16) is None
    assert store.list_page(limit=10, offset=0)[1] == 1


class _FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        return GenerationResult(text=self.text, model=self.model, input_tokens=10, output_tokens=5)

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.model, True, True, True)


def test_llm_review_baseline_scores_reported_findings_as_is(tmp_path: Path) -> None:
    case_dir = tmp_path / "c"
    write_tree(case_dir / "head", {"app.py": "def f(x):\n    return x > 1\n"})
    (case_dir / "change.patch").write_text("--- a/app.py\n+++ b/app.py\n")
    case = _case([Label(id="L1", category="logic_change", file="app.py", lines=(2, 2))])
    case.directory = case_dir
    response = {
        "findings": [
            {"file": "b/app.py", "start_line": 2, "end_line": 2, "category": "logic_change",
             "severity": "medium", "title": "boundary moved"},
            {"file": "app.py", "start_line": 1, "end_line": 1, "category": "not_a_category",
             "severity": "high", "title": "dropped"},
        ]
    }  # fmt: skip
    provider = _FakeProvider("Here you go: " + json.dumps(response))
    output = LLMReviewBaseline(provider, label="fake-model").run(case)
    assert output.error is None
    assert [(p.file, p.category, p.kind) for p in output.predictions] == [
        ("app.py", "logic_change", "ai")
    ]
    assert "    2 |     return x > 1" in provider.requests[0].user
    assert [label for label, _ in match_case(case, output.predictions).true_positives] == ["L1"]


def test_llm_review_baseline_records_unparseable_responses_as_failures(tmp_path: Path) -> None:
    case_dir = tmp_path / "c"
    (case_dir / "head").mkdir(parents=True)
    (case_dir / "change.patch").write_text("")
    case = _case([])
    case.directory = case_dir
    output = LLMReviewBaseline(_FakeProvider("no json here"), label="m").run(case)
    assert output.predictions == []
    assert output.error is not None and output.error.startswith("bad_response")
    assert parse_findings('{"findings": []}') == []


def test_cli_writes_every_format_from_one_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_tree(repo, {"app.py": "def f(x):\n    return x\n"})
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    (repo / "app.py").write_text(
        "def f(x):\n    try:\n        return x\n    except:\n        pass\n"
    )
    out = tmp_path / "out"
    out.mkdir()
    code = cli_main(
        ["analyze", "--git-repo", str(repo), "--base", "HEAD", "--format", "text",
         "--json-out", str(out / "r.json"), "--markdown-out", str(out / "r.md"),
         "--sarif-out", str(out / "r.sarif")]
    )  # fmt: skip
    assert code == 0
    report = json.loads((out / "r.json").read_text())
    sarif = json.loads((out / "r.sarif").read_text())
    assert report["summary"]["findings_total"] == len(sarif["runs"][0]["results"]) > 0
    assert (out / "r.md").read_text().startswith("# ChangeGuard report")
