from __future__ import annotations

from pathlib import Path

from changeguard.evaluation.dataset import Case, Label
from changeguard.evaluation.matching import Prediction, match_case
from changeguard.evaluation.metrics import Counts, bootstrap, micro
from changeguard.evaluation.reporting import compare_to_baseline
from changeguard.report.exporters import _fence, _md, to_markdown, to_sarif
from tests.conftest import ChangeRunner


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
