"""``changeguard eval`` subcommand."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from changeguard.evaluation.dataset import load_dataset
from changeguard.evaluation.reporting import compare_to_baseline, run_to_json, write_outputs
from changeguard.evaluation.runner import run_evaluation
from changeguard.evaluation.systems import (
    ChangedSymbolsBaseline,
    ChangeGuardSystem,
    KeywordBaseline,
    System,
)

DEFAULT_SYSTEMS = "changeguard,changeguard-diff-only,baseline-keyword,baseline-changed-symbols"


def _repo_root() -> Path:
    for parent in [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]:
        if (parent / "eval" / "dataset").is_dir():
            return parent
    return Path.cwd()


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def add_eval_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    root = _repo_root()
    p = sub.add_parser("eval", help="run the offline evaluation")
    p.add_argument("--dataset", type=Path, default=root / "eval" / "dataset")
    p.add_argument(
        "--split", choices=["dev", "holdout", "holdout-v2"], help="evaluate one split only"
    )
    p.add_argument(
        "--systems",
        default=DEFAULT_SYSTEMS,
        help=f"comma-separated systems (default: {DEFAULT_SYSTEMS})",
    )
    p.add_argument(
        "--ai",
        choices=["off", "replay", "record", "live"],
        default="off",
        help="add a changeguard+ai system",
    )
    p.add_argument("--ai-provider", default="ollama", choices=["ollama", "openai", "anthropic"])
    p.add_argument(
        "--ai-model",
        default="llama3.2:3b",
        help="comma-separated models; model@k for k-sample self-consistency",
    )
    p.add_argument("--ai-base-url", default=None)
    p.add_argument("--ai-samples", type=int, default=1, help="self-consistency samples per case")
    p.add_argument("--recordings", type=Path, default=root / "eval" / "recordings")
    p.add_argument("--out", type=Path, default=root / "eval" / "reports")
    p.add_argument(
        "--frontend-out", type=Path, default=root / "frontend" / "src" / "data" / "evaluation.json"
    )
    p.add_argument("--no-write", action="store_true", help="do not write report files")
    p.add_argument(
        "--check-baseline", type=Path, help="fail (exit 1) on regression against this baseline"
    )
    p.add_argument(
        "--update-baseline", type=Path, help="write the current results as the new baseline"
    )
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20261008)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_eval)


def _ai_systems(args: argparse.Namespace) -> tuple[list[System], dict[str, Any]]:
    """One AI system per model spec. ``model@k`` enables k-sample self-consistency voting."""
    from changeguard.ai.cache import MemoryCache
    from changeguard.ai.prompts import load_prompt
    from changeguard.ai.providers import _live
    from changeguard.ai.providers.base import LLMProvider
    from changeguard.ai.providers.replay import ReplayProvider
    from changeguard.ai.synthesizer import AISynthesizer
    from changeguard.config import Settings

    prompt = load_prompt()
    systems: list[System] = []
    models: list[dict[str, Any]] = []
    for spec in [m.strip() for m in args.ai_model.split(",") if m.strip()]:
        model, _, k = spec.partition("@")
        samples = int(k) if k else args.ai_samples
        settings = Settings(
            ai_provider=args.ai_provider,
            ai_model=model,
            ai_base_url=args.ai_base_url,
            ai_timeout_seconds=300,
        )
        directory = args.recordings / f"{args.ai_provider}-{_slug(model)}"
        live: LLMProvider | None = (
            _live(settings, args.ai_provider) if args.ai in ("record", "live") else None
        )
        provider: LLMProvider
        if args.ai == "live":
            assert live is not None
            provider = live
        else:
            provider = ReplayProvider(
                directory, model=model, live=live, record=args.ai == "record",
                prompt_id=prompt.id, prompt_version=prompt.version, provider_label=args.ai_provider,
            )  # fmt: skip
        synthesizer = AISynthesizer(provider, cache=MemoryCache(), prompt=prompt, samples=samples)
        suffix = f"@{samples}" if samples > 1 else ""
        systems.append(
            ChangeGuardSystem(
                f"changeguard+ai:{model}{suffix}",
                description=f"Rules + AI synthesis ({args.ai_provider}/{model}"
                + (f", {samples}-sample self-consistency" if samples > 1 else "")
                + f", {args.ai})",
                synthesizer=synthesizer,
            )
        )
        models.append(
            {
                "model": model,
                "samples": samples,
                "recordings": str(directory.name) if args.ai != "live" else None,
            }
        )
    info = {
        "mode": args.ai,
        "provider": args.ai_provider,
        "models": models,
        "prompt_id": prompt.id,
        "prompt_version": prompt.version,
        "prompt_sha256": prompt.sha256,
        "decoding": {"temperature": 0.0, "seed": 7, "self_consistency_temperature": 0.7},
    }
    return systems, info


def build_systems(names: list[str]) -> list[System]:
    factories: dict[str, System] = {
        "changeguard": ChangeGuardSystem(),
        "changeguard-diff-only": ChangeGuardSystem(
            "changeguard-diff-only",
            description="Same rules without the repository snapshot (ablation)",
            force_diff_only=True,
        ),
        "changeguard-no-tests": ChangeGuardSystem(
            "changeguard-no-tests",
            description="Without test mapping (ablation)",
            disabled_stages=frozenset({"tests"}),
        ),
        "baseline-keyword": KeywordBaseline(),
        "baseline-changed-symbols": ChangedSymbolsBaseline(),
    }
    unknown = [n for n in names if n not in factories]
    if unknown:
        raise SystemExit(
            f"unknown system(s): {', '.join(unknown)}; choose from {', '.join(factories)}"
        )
    return [factories[n] for n in names]


def cmd_eval(args: argparse.Namespace) -> int:
    cases = load_dataset(args.dataset, split=args.split)
    if not cases:
        print(f"no cases found under {args.dataset}", file=sys.stderr)
        return 2
    systems = build_systems([s.strip() for s in args.systems.split(",") if s.strip()])
    ai_info: dict[str, Any] = {"mode": "off"}
    if args.ai != "off":
        ai_systems, ai_info = _ai_systems(args)
        systems[1:1] = ai_systems
    run = run_evaluation(
        cases,
        systems,
        bootstrap_samples=args.bootstrap,
        seed=args.seed,
        progress=not args.quiet,
        ai_info=ai_info,
    )
    data = run_to_json(run)
    for s in data["systems"]:
        o = s["overall"]
        neg = s["negative_controls"]
        print(
            f"{s['system']:<26} P={_pct(o['precision'])} R={_pct(o['recall'])} F1={_pct(o['f1'])} "
            f"negFP={_pct(neg['false_positive_rate'])} unsupported={s['evidence']['unsupported_findings']}",
        )
    if not args.no_write and args.split is None:
        for path in write_outputs(data, args.out, frontend_path=args.frontend_out):
            print(f"wrote {path}", file=sys.stderr)
    if args.update_baseline:
        args.update_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.update_baseline.write_text(
            json.dumps({k: data[k] for k in ("manifest", "systems", "cases")}, indent=2) + "\n"
        )
        print(f"updated baseline {args.update_baseline}", file=sys.stderr)
    if args.check_baseline:
        baseline = json.loads(args.check_baseline.read_text())
        result = compare_to_baseline(data, baseline)
        for message in result.messages:
            print(("✓ " if result.passed else "✗ ") + message)
        return 0 if result.passed else 1
    return 0


def _pct(value: float | None) -> str:
    return "  —  " if value is None else f"{value * 100:5.1f}%"
