"""AI synthesis stage: generation → validation → grounding verification → merge.

Invariants (enforced in code and covered by tests):

1. The model can only *add* information. It cannot remove, re-rank, or edit
   deterministic findings; its output lands in ``Finding.ai_analysis`` or in
   new findings with ``kind = "ai"``.
2. Every accepted claim cites evidence that ChangeGuard produced, and AI
   finding locations are derived from that evidence, never from model text.
3. AI findings are capped at severity ``high`` and confidence ``medium``.
4. Any provider failure degrades to the deterministic report, recorded in
   the trace.
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from changeguard.ai.cache import NullCache, ResponseCache
from changeguard.ai.context import ContextPack, build_context
from changeguard.ai.grounding import GroundingVerifier
from changeguard.ai.prompts import PromptTemplate, load_prompt
from changeguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    ProviderError,
)
from changeguard.ai.schemas import (
    AI_CATEGORIES,
    AdditionalRisk,
    OutputParseError,
    ReviewOutput,
    parse_review,
    review_json_schema,
)
from changeguard.analysis.context import AnalysisContext
from changeguard.analysis.pipeline import STAGE_LABELS, SynthesisOutcome
from changeguard.analysis.rules.catalog import Rule
from changeguard.report.models import (
    AIAnalysis,
    AISummary,
    AIVerification,
    Category,
    Confidence,
    Explanation,
    FindingKind,
    Location,
    ModelCallTrace,
    RejectedClaim,
    Severity,
    StageResult,
    SuggestedTest,
)

MAX_RISKS = 3
_MAX_TEXT = 900
_MAX_CODE = 2000


@dataclass(slots=True)
class _Sample:
    output: ReviewOutput
    result: GenerationResult


def _clip(text: str, limit: int = _MAX_TEXT) -> str:
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


class AISynthesizer:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        cache: ResponseCache | None = None,
        prompt: PromptTemplate | None = None,
        max_context_chars: int = 24_000,
        max_findings: int = 8,
        temperature: float = 0.0,
        seed: int | None = 7,
        samples: int = 1,
        max_output_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.cache = cache or NullCache()
        self.prompt = prompt or load_prompt()
        self.max_context_chars = max_context_chars
        self.max_findings = max_findings
        self.temperature = temperature
        self.seed = seed
        self.samples = max(1, samples)
        self.max_output_tokens = max_output_tokens

    # -- request construction -----------------------------------------------------

    def _request(self, pack: ContextPack, *, sample: int) -> GenerationRequest:
        user = self.prompt.render_user(
            change_summary=pack.change_summary,
            findings=pack.findings_text,
            evidence=pack.evidence_text or "(no evidence items)",
            finding_ids=", ".join(f.id for f in pack.findings) or "none",
            max_risks=str(MAX_RISKS),
            evidence_ids=", ".join(pack.evidence_ids) or "none",
            categories=", ".join(AI_CATEGORIES),
        )
        varied = self.samples > 1 and sample > 0
        return GenerationRequest(
            system=self.prompt.system,
            user=user,
            schema=review_json_schema(),
            max_output_tokens=self.max_output_tokens,
            temperature=0.7 if varied else self.temperature,
            seed=(self.seed + sample) if self.seed is not None else None,
        )

    def _trace(
        self, request: GenerationRequest, result: GenerationResult | None, *, started: str, latency: float,
        status: str, cache_hit: bool, attempts: int, error: str | None = None,
    ) -> ModelCallTrace:  # fmt: skip
        return ModelCallTrace(
            call_id=uuid.uuid4().hex[:12],
            provider=self.provider.name,
            model=result.model if result is not None else self.provider.model,
            prompt_id=self.prompt.id,
            prompt_version=self.prompt.version,
            prompt_sha256=self.prompt.sha256,
            request_sha256=request.fingerprint(
                self.provider.name, self.provider.model, self.prompt.id, self.prompt.version
            ),
            started_at=started,
            latency_ms=round(latency, 1),
            input_tokens=result.input_tokens if result is not None else None,
            output_tokens=result.output_tokens if result is not None else None,
            cache_hit=cache_hit,
            attempts=attempts,
            status=status,  # type: ignore[arg-type]
            error=error,
        )

    def _generate(self, request: GenerationRequest, traces: list[ModelCallTrace]) -> _Sample | None:
        key = request.fingerprint(
            self.provider.name, self.provider.model, self.prompt.id, self.prompt.version
        )
        started = datetime.now(UTC).isoformat(timespec="seconds")
        cached = self.cache.get(key)
        if cached is not None:
            try:
                output = parse_review(cached.text)
                traces.append(
                    self._trace(
                        request,
                        cached,
                        started=started,
                        latency=0.0,
                        status="ok",
                        cache_hit=True,
                        attempts=0,
                    )
                )
                return _Sample(output, cached)
            except OutputParseError:
                pass  # stale or corrupt entry: regenerate
        attempt_request = request
        for attempt in (1, 2):
            t0 = time.perf_counter()
            try:
                result = self.provider.generate(attempt_request)
            except ProviderError as exc:
                status = "timeout" if exc.kind == "timeout" else "error"
                traces.append(
                    self._trace(
                        attempt_request,
                        None,
                        started=started,
                        latency=(time.perf_counter() - t0) * 1000,
                        status=status,
                        cache_hit=False,
                        attempts=attempt,
                        error=f"{exc.kind}: {exc.message}",
                    )
                )
                return None
            latency = result.latency_ms or (time.perf_counter() - t0) * 1000
            try:
                output = parse_review(result.text)
            except OutputParseError as exc:
                traces.append(
                    self._trace(
                        attempt_request,
                        result,
                        started=started,
                        latency=latency,
                        status="invalid_output",
                        cache_hit=False,
                        attempts=attempt,
                        error=str(exc),
                    )
                )
                # One repair attempt: show the model its own validation error.
                attempt_request = GenerationRequest(
                    system=request.system,
                    user=request.user
                    + f"\n\nYour previous reply was rejected ({exc}). Reply again with a single JSON object that matches the schema exactly.",
                    schema=request.schema,
                    max_output_tokens=request.max_output_tokens,
                    temperature=request.temperature,
                    seed=request.seed,
                )
                continue
            traces.append(
                self._trace(
                    attempt_request,
                    result,
                    started=started,
                    latency=latency,
                    status="ok",
                    cache_hit=False,
                    attempts=attempt,
                )
            )
            self.cache.put(key, result, provider=self.provider.name)
            return _Sample(output, result)
        return None

    # -- stage ------------------------------------------------------------------------

    def run(self, ctx: AnalysisContext) -> SynthesisOutcome:
        t0 = time.perf_counter()
        pack = build_context(ctx, max_chars=self.max_context_chars, max_findings=self.max_findings)
        traces: list[ModelCallTrace] = []
        samples: list[_Sample] = []
        for i in range(self.samples):
            sample = self._generate(self._request(pack, sample=i), traces)
            if sample is not None:
                samples.append(sample)
            elif i == 0:
                break  # the provider is failing; do not burn more attempts
        synth_ms = (time.perf_counter() - t0) * 1000
        base_summary: dict[str, object] = {
            "provider": self.provider.name,
            "model": samples[0].result.model if samples else self.provider.model,
            "prompt_id": self.prompt.id,
            "prompt_version": self.prompt.version,
            "prompt_sha256": self.prompt.sha256,
            "samples": self.samples,
            "context_chars": pack.chars,
            "context_truncated": pack.truncated,
            "calls": traces,
        }
        if not samples:
            last_error = next((t.error for t in reversed(traces) if t.error), "no response")
            summary = AISummary.model_validate(
                {
                    **base_summary,
                    "status": "failed",
                    "note": f"AI synthesis unavailable ({last_error}); the deterministic report is complete.",
                }
            )
            return SynthesisOutcome(
                summary=summary,
                synthesis=StageResult(name="synthesis", label=STAGE_LABELS["synthesis"], status="failed", duration_ms=round(synth_ms, 2),
                                      summary={"calls": len(traces)}, notes=[last_error or "no response"]),
                verification=StageResult(name="verification", label=STAGE_LABELS["verification"], status="skipped", duration_ms=0.0,
                                         notes=["nothing to verify"]),
            )  # fmt: skip

        t1 = time.perf_counter()
        verification, notes_applied, risks_added, assessment = self._verify_and_merge(
            ctx, pack, samples
        )
        verify_ms = (time.perf_counter() - t1) * 1000
        summary = AISummary.model_validate(
            {
                **base_summary,
                "status": "completed",
                "verification": verification,
                "overall_assessment": assessment,
            }
        )
        tokens_in = sum(t.input_tokens or 0 for t in traces)
        tokens_out = sum(t.output_tokens or 0 for t in traces)
        return SynthesisOutcome(
            summary=summary,
            synthesis=StageResult(
                name="synthesis", label=STAGE_LABELS["synthesis"], status="ok", duration_ms=round(synth_ms, 2),
                summary={"model": summary.model, "calls": len(traces), "input_tokens": tokens_in, "output_tokens": tokens_out,
                         "cache_hits": sum(1 for t in traces if t.cache_hit), "context_chars": pack.chars, "truncated": pack.truncated},
            ),
            verification=StageResult(
                name="verification", label=STAGE_LABELS["verification"],
                status="warning" if verification.claims_rejected else "ok", duration_ms=round(verify_ms, 2),
                summary={"claims": verification.claims_total, "accepted": verification.claims_accepted,
                         "rejected": verification.claims_rejected, "notes_applied": notes_applied, "ai_findings": risks_added},
            ),
        )  # fmt: skip

    # -- verification and merge ------------------------------------------------------

    def _verify_and_merge(
        self, ctx: AnalysisContext, pack: ContextPack, samples: list[_Sample]
    ) -> tuple[AIVerification, int, int, str | None]:
        finding_ids = {f.id for f in pack.findings}
        verifier = GroundingVerifier(pack, finding_ids)
        verification = AIVerification()
        model = samples[0].result.model
        primary = samples[0].output

        def reject(target: str, summary: str, reasons: list[str]) -> None:
            verification.claims_rejected += 1
            verification.rejected.append(
                RejectedClaim(target=target, summary=_clip(summary, 160), reasons=reasons)
            )

        # Finding notes come from the primary sample.
        notes_applied = 0
        seen_targets: set[str] = set()
        by_id = {f.id: f for f in ctx.findings}
        for note in primary.finding_notes:
            verification.claims_total += 1
            target = by_id.get(note.finding_id)
            verdict = verifier.check_note(
                note, f"{target.title}\n{target.description}" if target else ""
            )
            if note.finding_id in seen_targets:
                verdict.accepted, verdict.reasons = (
                    False,
                    ["duplicate: a note for this finding was already accepted"],
                )
            if not verdict.accepted:
                reject(note.finding_id, note.explanation, verdict.reasons)
                continue
            seen_targets.add(note.finding_id)
            verification.claims_accepted += 1
            finding = by_id[note.finding_id]
            finding.ai_analysis = AIAnalysis(
                explanation=_clip(note.explanation),
                failure_scenario=_clip(note.failure_scenario),
                suggested_test=SuggestedTest(
                    description=_clip(note.suggested_test.description, 500),
                    code=_clip(note.suggested_test.code, _MAX_CODE) or None,
                    kind="unit",
                    language=finding.suggested_test.language,
                    source="ai",
                ),
                confidence=Confidence(note.confidence),
                uncertainty=_clip(note.uncertainty, 400),
                evidence_ids=list(dict.fromkeys(note.evidence_ids)),
                model=model,
            )
            notes_applied += 1

        # Additional risks: verified per sample, then (with sampling) kept only if a
        # majority of samples propose a matching risk.
        verified: list[list[AdditionalRisk]] = []
        for i, sample in enumerate(samples):
            accepted: list[AdditionalRisk] = []
            for risk in sample.output.additional_risks[:MAX_RISKS]:
                verdict = verifier.check_risk(risk)
                if i == 0:
                    verification.claims_total += 1
                    if not verdict.accepted:
                        reject("additional_risk", risk.title, verdict.reasons)
                        continue
                    verification.claims_accepted += 1
                elif not verdict.accepted:
                    continue
                accepted.append(risk)
            verified.append(accepted)

        risks_added = 0
        for risk in verified[0]:
            support = 1.0
            if len(samples) > 1:
                agreeing = (
                    sum(1 for other in verified[1:] if any(_same_risk(risk, o) for o in other)) + 1
                )
                support = agreeing / len(samples)
                if support < 0.5:
                    reject(
                        "additional_risk",
                        risk.title,
                        [f"low_agreement: proposed by {agreeing} of {len(samples)} samples"],
                    )
                    verification.claims_accepted -= 1
                    continue
            if self._add_risk(ctx, pack, risk, model, support):
                risks_added += 1

        assessment: str | None = None
        if primary.overall_assessment.strip():
            verification.claims_total += 1
            verdict = verifier.check_text(primary.overall_assessment)
            if verdict.accepted:
                verification.claims_accepted += 1
                assessment = _clip(primary.overall_assessment, 600)
            else:
                reject("overall_assessment", primary.overall_assessment, verdict.reasons)
        return verification, notes_applied, risks_added, assessment

    def _add_risk(
        self,
        ctx: AnalysisContext,
        pack: ContextPack,
        risk: AdditionalRisk,
        model: str,
        support: float,
    ) -> bool:
        evidence = {e.id: e for e in pack.evidence}
        anchor = next(
            (
                evidence[e]
                for e in risk.evidence_ids
                if e in evidence and evidence[e].file and evidence[e].start_line
            ),
            None,
        )
        if anchor is None or anchor.file is None:
            return False
        category = Category(risk.category)
        start = anchor.start_line
        end = anchor.end_line or start
        # Corroboration instead of duplication: a matching deterministic finding absorbs the AI risk.
        for f in ctx.findings:
            if (
                f.kind is not FindingKind.AI
                and f.category == category
                and f.location.file == anchor.file
                and f.location.start_line is not None
                and start is not None
                and f.location.start_line <= (end or start) + 2
                and start <= (f.location.end_line or f.location.start_line) + 2
            ):
                if "ai" not in f.corroborated_by:
                    f.corroborated_by.append("ai")
                return False
        severity = Severity(risk.severity)
        confidence = Confidence(risk.confidence)
        rule = Rule("AI-RISK", "AI-identified risk", category, FindingKind.AI, severity,
                    "Proposed by a language model and verified to cite real evidence; not established by deterministic analysis.")  # fmt: skip
        finding = ctx.add_finding(
            "AI-RISK",
            rule=rule,
            title=_clip(risk.title, 140),
            description=_clip(risk.description),
            location=Location(
                file=anchor.file, start_line=start, end_line=end, side=anchor.side or "head"
            ),
            evidence_ids=list(dict.fromkeys(risk.evidence_ids)),
            failure_scenario=_clip(risk.failure_scenario),
            suggested_test=SuggestedTest(
                description=_clip(risk.suggested_test.description, 500),
                code=_clip(risk.suggested_test.code, _MAX_CODE) or None,
                kind="unit",
                source="ai",
            ),
            severity=severity,
            confidence=confidence,
            kind=FindingKind.AI,
            category=category,
            tags=["ai"],
            discriminator=risk.title,
        )
        finding.explanation = Explanation(
            text=f"Proposed by {model} and verified to cite evidence produced by ChangeGuard. "
            f"Uncertainty: {_clip(risk.uncertainty, 300)}",
            source="ai",
            model=model,
            uncertainty=_clip(risk.uncertainty, 300),
            evidence_ids=list(dict.fromkeys(risk.evidence_ids)),
        )
        finding.ai_analysis = AIAnalysis(
            explanation=_clip(risk.description),
            failure_scenario=_clip(risk.failure_scenario),
            suggested_test=finding.suggested_test,
            confidence=confidence,
            uncertainty=_clip(risk.uncertainty, 400),
            evidence_ids=finding.evidence_ids,
            model=model,
            support=round(support, 3) if self.samples > 1 else None,
        )
        return True


def _same_risk(a: AdditionalRisk, b: AdditionalRisk) -> bool:
    """Two proposed risks agree if they share a category and at least one cited evidence item."""
    return a.category == b.category and bool(set(a.evidence_ids) & set(b.evidence_ids))


def evidence_usage(samples: list[ReviewOutput]) -> Counter[str]:
    """How often each evidence id is cited across samples (diagnostics for evaluation)."""
    counts: Counter[str] = Counter()
    for s in samples:
        for n in s.finding_notes:
            counts.update(n.evidence_ids)
        for r in s.additional_risks:
            counts.update(r.evidence_ids)
    return counts
