"""Export static data the web UI renders without calling the engine.

* ``rules.json``          — the rule catalog (for the System card page)
* ``sample.json``         — the billing sample's labelled metadata (guided experience)
* ``sample-report.json``  — a real report for the billing sample (landing page figures)
* ``sample-report-ai.json`` — the same analysis with AI synthesis from a local model
                              (only with ``--with-ai MODEL``; requires Ollama)
* ``<public>/samples/<id>/report.{json,md,sarif}`` — the recorded report's exports, rendered
                              by the engine's own exporters (static report page downloads)

The sample report is produced by running the actual pipeline (no AI) on the
bundled synthetic sample, so the landing page shows genuine output.

    uv run python tools/export_frontend_data.py ../frontend/src/data [--with-ai llama3.2:3b]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from changeguard.analysis.context import AnalysisOptions
from changeguard.analysis.pipeline import AnalysisPipeline
from changeguard.analysis.rules.catalog import all_rules
from changeguard.config import Settings
from changeguard.ingest.prepare import prepare_input
from changeguard.report.exporters import to_json, to_markdown, to_sarif_json
from changeguard.report.models import Report
from changeguard.samples import get_sample


def write_exports(report: Report, public_dir: Path) -> Path:
    """Write the engine's own JSON / Markdown / SARIF renderings of a recorded report."""
    target = public_dir / "samples" / "billing-refactor"
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.json").write_text(to_json(report))
    (target / "report.md").write_text(to_markdown(report))
    (target / "report.sarif").write_text(to_sarif_json(report))
    return target


def main(out_dir: Path, ai_model: str | None = None, public_dir: Path | None = None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rules.json").write_text(json.dumps(all_rules(), indent=2) + "\n")

    sample = get_sample("billing-refactor")
    if sample is None:
        raise SystemExit("billing-refactor sample is missing")
    coverage = sample.coverage_path
    prepared = prepare_input(
        Settings(),
        patch=sample.patch_text,
        archive=sample.archive(),
        coverage=coverage.read_bytes() if coverage else None,
    )
    report = AnalysisPipeline().run(
        prepared,
        analysis_id="sample-billing-refactor",
        created_at="2026-10-08T00:00:00Z",
        options=AnalysisOptions(title=f"Sample: {sample.title}"),
    )
    (out_dir / "sample-report.json").write_text(report.model_dump_json(indent=2) + "\n")
    meta = {
        "id": sample.id,
        "title": sample.title,
        "tagline": sample.tagline,
        "description": sample.description,
        "language": sample.language,
        "highlights": list(sample.highlights),
        "synthetic": bool(sample.extra.get("synthetic", True)),
        "base_files": sample.base_files(),
        "coverage_filename": coverage.name if coverage else None,
    }
    (out_dir / "sample.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {out_dir}/rules.json and sample-report.json ({len(report.findings)} findings)",
        file=sys.stderr,
    )
    if ai_model:
        from changeguard.ai.providers.ollama import OllamaProvider
        from changeguard.ai.synthesizer import AISynthesizer

        synthesizer = AISynthesizer(OllamaProvider(ai_model, timeout=600))
        ai_report = AnalysisPipeline(synthesizer=synthesizer).run(
            prepared,
            analysis_id="sample-billing-refactor-ai",
            created_at="2026-10-08T00:00:00Z",
            options=AnalysisOptions(title=f"Sample: {sample.title}", ai_enabled=True),
        )
        (out_dir / "sample-report-ai.json").write_text(ai_report.model_dump_json(indent=2) + "\n")
        v = ai_report.ai.verification
        print(
            f"wrote sample-report-ai.json (AI {ai_report.ai.status}; "
            f"{v.claims_accepted if v else 0}/{v.claims_total if v else 0} claims verified)",
            file=sys.stderr,
        )
    if public_dir is not None:
        recorded_ai = out_dir / "sample-report-ai.json"
        recorded = (
            Report.model_validate_json(recorded_ai.read_text()) if recorded_ai.exists() else report
        )
        target = write_exports(recorded, public_dir)
        print(f"wrote exports of {recorded.analysis_id} to {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", nargs="?", default="../frontend/src/data", type=Path)
    parser.add_argument("--with-ai", dest="ai_model", default=None)
    parser.add_argument("--public-dir", default="../frontend/public", type=Path)
    args = parser.parse_args()
    raise SystemExit(main(args.out_dir, args.ai_model, args.public_dir))
