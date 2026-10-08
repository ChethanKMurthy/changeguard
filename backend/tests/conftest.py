from __future__ import annotations

import io
import sys
import textwrap
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_patch import make_patch  # noqa: E402

from changeguard.analysis.context import AnalysisOptions  # noqa: E402
from changeguard.analysis.pipeline import AnalysisPipeline, Synthesizer  # noqa: E402
from changeguard.config import Settings  # noqa: E402
from changeguard.ingest.prepare import prepare_input  # noqa: E402
from changeguard.report.models import Report  # noqa: E402


def dedent(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content))


def zip_bytes(files: dict[str, str], prefix: str = "") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for rel, content in files.items():
            zf.writestr(prefix + rel, dedent(content))
    return buffer.getvalue()


ChangeRunner = Callable[..., Report]


@pytest.fixture
def run_change(tmp_path: Path) -> ChangeRunner:
    """Build base/head trees, diff them with git, and run the full pipeline."""

    def run(
        base: dict[str, str],
        head: dict[str, str],
        *,
        snapshot: bool = True,
        coverage: bytes | None = None,
        synthesizer: Synthesizer | None = None,
        ai: bool = False,
    ) -> Report:
        base_dir, head_dir = tmp_path / "base", tmp_path / "head"
        write_tree(base_dir, base)
        write_tree(head_dir, head)
        patch = make_patch(base_dir, head_dir)
        prepared = prepare_input(
            Settings(),
            patch=patch,
            archive=zip_bytes(base) if snapshot else None,
            coverage=coverage,
        )
        return AnalysisPipeline(synthesizer=synthesizer).run(
            prepared,
            analysis_id="test",
            created_at="2026-01-01T00:00:00Z",
            options=AnalysisOptions(ai_enabled=ai),
        )

    return run


def rules(report: Report) -> list[str]:
    return [f.rule_id for f in report.findings]
