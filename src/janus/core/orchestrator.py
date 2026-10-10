"""PipelineOrchestrator — wires the tiers into one loop (DIP: interfaces
injected, never constructed here).

CODE_MODIFICATION pipeline:
  S1 decide → prune AST slices → S2 generate → parse → apply →
  write → verify → on failure: triage → ONE repair attempt →
  on final failure: restore original files byte-for-byte (restore-parity).

Escalation and non-modification intents return immediately without any
generative inference.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from janus.context.ast_pruner import extract_symbol, mentioned_symbols, symbol_names
from janus.core.config import JanusSettings
from janus.core.governor import LoadGovernor, LoadSaturatedError
from janus.core.types import (
    IntentType,
    PatchBlock,
    System1Decision,
    VerificationResult,
)
from janus.patcher.engine import PatchApplicationError, apply_all
from janus.patcher.parser import PatchParseError, parse_patches
from janus.system1.base import DecisionEngineProtocol
from janus.system2.base import GenerativeEngineProtocol
from janus.system2.client import GenerationError
from janus.system2.prompt_templates import build_user_prompt
from janus.verification.runner import VerificationRunner
from janus.verification.triage import triage_failure


def _safe_path(repo_root: str, rel: str) -> Path:
    """Resolve a patch/slice target and refuse escapes from the repo.

    P0-1 (audit 2026-09-24): model output is untrusted BY DESIGN; the
    write path must enforce that belief.
    """
    root = Path(repo_root).resolve()
    resolved = (root / rel).resolve()
    if resolved != root and root not in resolved.parents:
        raise PatchApplicationError(f"path escapes repo root: {rel!r}")
    return resolved


def _whole_slice_fallback(raw: str, slices: dict[str, str]) -> list[PatchBlock]:
    """A real qwen3-4b failure mode (harvested 2026-09-24): the model
    replies `file: <path>` + the full corrected slice with no markers.
    Deterministic rescue: if the text names exactly one sliced file, treat
    everything after the header as the replacement for the whole slice.
    Only whole-slice replacement — never a partial guess."""
    named = [rel for rel in slices if f"file: {rel}" in raw]
    if len(named) != 1:
        return []
    rel = named[0]
    body = raw.split(f"file: {rel}", 1)[1].strip()
    if body.startswith("```"):  # strip code fencing if present
        body_lines = body.splitlines()
        body = "\n".join(
            body_lines[1:-1] if body_lines[-1].startswith("```") else body_lines[1:]
        )
    if not body:
        return []
    return [PatchBlock(file_path=rel, search_block=slices[rel], replace_block=body)]


class RunStatus(StrEnum):
    PATCHED_VERIFIED = "patched_verified"
    ESCALATE = "escalate"
    READ_ONLY = "read_only"
    DIRECT_ACTION = "direct_action"
    FAILED_ROLLED_BACK = "failed_rolled_back"


class RunReport(BaseModel):
    status: RunStatus
    decision: System1Decision
    patches: list[PatchBlock] = Field(default_factory=list)
    verification: VerificationResult | None = None
    repair_note: str | None = None
    message: str = ""
    arbitration: dict | None = None  # JB-3: {candidates, chosen, scores} when S1 ranked


def _fit_slices(slices: dict[str, str], budget_chars: int = 40_000) -> dict[str, str]:
    """Cap the total slice context to the S2's prompt budget.

    Dogfood 2026-10-10: the no-gate ablation's repair prompt hit 16,805
    tokens against the llama-server's 16,384-token context → 400 Bad
    Request. Same failure class as the S1 decider's 2050-token limit —
    the context budget is a hard ceiling, so the slices' total must fit
    it with room for the system prompt and the generation. Per-file
    budget when over, head+tail kept so signatures and usage survive.
    """
    total = sum(len(v) for v in slices.values())
    if total <= budget_chars:
        return slices
    per_file = budget_chars // len(slices)
    fitted: dict[str, str] = {}
    for path, code in slices.items():
        if len(code) <= per_file:
            fitted[path] = code
        else:
            head = per_file * 3 // 4
            tail = per_file - head
            marker = "\n...[truncated for context budget]...\n"
            fitted[path] = code[:head] + marker + code[-tail:]
    return fitted


class PipelineOrchestrator:
    def __init__(
        self,
        s1: DecisionEngineProtocol,
        s2: GenerativeEngineProtocol,
        runner: VerificationRunner | None = None,
        settings: JanusSettings | None = None,
    ) -> None:
        self._s1 = s1
        self._s2 = s2
        self._settings = settings or JanusSettings()
        self._runner = runner or VerificationRunner(self._settings)

    def run(self, user_prompt: str, repo_root: str, repo_summary: str) -> RunReport:
        decision = self._s1.evaluate(user_prompt, repo_summary)

        if decision.intent == IntentType.UNCLEAR_ESCALATE:
            return RunReport(
                status=RunStatus.ESCALATE,
                decision=decision,
                message=(
                    f"confidence {decision.confidence:.2f} below threshold; "
                    "clarify the request"
                ),
            )
        if decision.intent == IntentType.EXPLANATION:
            return RunReport(status=RunStatus.READ_ONLY, decision=decision)
        if decision.intent == IntentType.DIRECT_ACTION:
            return RunReport(status=RunStatus.DIRECT_ACTION, decision=decision)

        return self.run_modify(decision, repo_root)

    def run_forced(self, decision: System1Decision, repo_root: str) -> RunReport:
        """Public API for executing a modification pipeline against a
        caller-supplied decision (e.g. after the human overrides an
        escalation). The decision is treated as authoritative — the gate
        has already had its say."""
        return self.run_modify(decision, repo_root)

    # ------------------------------------------------------------------

    def run_modify(self, decision: System1Decision, repo_root: str) -> RunReport:
        slices = self._collect_slices(decision, repo_root)
        if not slices:
            return RunReport(
                status=RunStatus.ESCALATE,
                decision=decision,
                message="no matching symbols/files could be sliced; clarify targets",
            )
        slices = _fit_slices(slices)

        originals: dict[str, str | None] = {}  # None = file did not exist
        repair_note: str | None = None
        last_error = ""

        for _attempt in range(1 + self._settings.max_repair_attempts):
            prompt = build_user_prompt(
                decision.micro_instruction, slices, repair_note=repair_note
            )
            try:
                raw, arbitration = self._generate_and_rank(
                    prompt, decision.micro_instruction
                )
                patches = parse_patches(raw)
            except LoadSaturatedError as e:
                # backpressure timeout is an environment finding, not a
                # model failure: stop cleanly, nothing applied yet (P0-2)
                self._restore(originals, repo_root)
                return RunReport(
                    status=RunStatus.FAILED_ROLLED_BACK,
                    decision=decision,
                    repair_note=repair_note,
                    message=f"load-saturated: {e}; originals restored",
                )
            except (GenerationError, PatchParseError) as e:
                # Model-side failures are retry data. Everything else is a
                # bug in OUR code and must crash loudly (P0-3).
                last_error = f"{type(e).__name__}: {e}"
                repair_note = f"generation failed: {last_error}"
                continue
            if not patches:
                patches = _whole_slice_fallback(raw, slices)
            if not patches:
                last_error = "model output contained no patch blocks"
                repair_note = (
                    "your previous reply had no valid "
                    "<<<<<<< SEARCH / ======= / >>>>>>> REPLACE blocks"
                )
                continue

            try:
                self._apply_and_write(patches, repo_root, originals, set(slices))
            except PatchApplicationError as e:
                last_error = str(e)
                repair_note = f"patch did not match the code: {e}"
                continue

            verification = self._runner.run(repo_root)
            if verification.passed:
                return RunReport(
                    status=RunStatus.PATCHED_VERIFIED,
                    decision=decision,
                    patches=patches,
                    verification=verification,
                    repair_note=repair_note,
                    arbitration=arbitration,
                )

            repair_note = triage_failure(verification, repo_root)
            last_error = repair_note

        self._restore(originals, repo_root)
        return RunReport(
            status=RunStatus.FAILED_ROLLED_BACK,
            decision=decision,
            repair_note=repair_note,
            message=f"all attempts failed, files restored. Last error: {last_error}",
        )

    # ------------------------------------------------------------------

    def _generate_and_rank(
        self, prompt: str, instruction: str
    ) -> tuple[str, dict | None]:
        """JB-3: when s1_rank_candidates > 0, draw N candidates and let S1
        pick the champion; verification remains the judge either way."""
        n = self._settings.s1_rank_candidates
        gov = LoadGovernor(
            limit=self._settings.s2_loadavg_limit,
            timeout_s=self._settings.s2_loadavg_timeout,
        )
        if n <= 1:
            gov.wait()
            return self._s2.generate_patch(prompt), None
        gov.wait()
        gen_multi = getattr(self._s2, "generate_patches", None)
        candidates: list[str]
        if callable(gen_multi):
            candidates = gen_multi(prompt, n)
        else:
            candidates = [self._s2.generate_patch(prompt)]
        if len(candidates) <= 1:
            return candidates[0], None
        rank = getattr(self._s1, "rank_patches", None)
        order: list[int] = (
            list(rank(instruction, candidates)) if callable(rank) else list(range(len(candidates)))
        )
        chosen = order[0]
        return candidates[chosen], {
            "candidates": len(candidates),
            "chosen": chosen,
            "order": order,
        }

    def _collect_slices(
        self, decision: System1Decision, repo_root: str
    ) -> dict[str, str]:
        slices: dict[str, str] = {}
        for rel in decision.target_files:
            path = Path(repo_root) / rel
            try:
                path = _safe_path(repo_root, rel)
                source = path.read_text(encoding="utf-8")
            except PatchApplicationError:
                raise  # traversal must not silently become "no slices"
            except (OSError, UnicodeDecodeError):
                continue
            symbols = decision.target_symbols
            if not symbols:
                # Deterministic symbol targeting: prompt mentions a symbol
                # named verbatim in the file -> slice it (works in mock too).
                lang = "javascript" if rel.endswith((".js", ".mjs", ".ts")) else "python"
                symbols = mentioned_symbols(decision.micro_instruction, source, lang)
            if symbols:
                for symbol in symbols:
                    slice_ = extract_symbol(
                        source,
                        symbol,
                        language="javascript" if rel.endswith((".js", ".mjs", ".ts")) else "python",
                    )
                    if slice_ is not None:
                        slices[rel] = slice_
            elif len(source) < 12_000:
                # Small file: whole-file slice is the honest context.
                slices[rel] = source
            else:
                # Big file with no verbatim symbol: whole-file exceeds the
                # S2's context budget, symbol-less extraction starves the
                # repair. Extract the file's top-level symbols and let the
                # S1 arbitrate which earns the slice — the same noul
                # treatment file targeting already gets. (Dogfood
                # 2026-10-08: external fixtures point at click's
                # _termui_impl.py, way over 12K, prompts name no symbol
                # verbatim → zero slices → ESCALATE.)
                lang = "javascript" if rel.endswith((".js", ".mjs", ".ts")) else "python"
                cands: list[tuple[str, str]] = []
                for name in symbol_names(source, lang):
                    slice_ = extract_symbol(source, name, language=lang)
                    if slice_ is not None:
                        cands.append((name, slice_))
                if cands:
                    # The S1 decider enforces a 1-2050 token prompt limit
                    # (measured 2026-10-08: 38 questions with code stubs
                    # = 10.8K tokens -> 400 Bad Request). Cap the field to
                    # 16 candidates and keep each preview tiny so the rank
                    # question batch fits the budget.
                    cands = cands[:16]
                    ranked = self._s1.rank_patches(
                        decision.micro_instruction,
                        [f"{name}:\n{text[:150]}" for name, text in cands],
                    )
                    slices[rel] = cands[ranked[0]][1]
        return slices

    def _apply_and_write(
        self,
        patches: list[PatchBlock],
        repo_root: str,
        originals: dict[str, str | None],
        candidate_files: set[str] | None = None,
    ) -> None:
        """Apply in memory per file; write only if every patch for that
        file applies. Originals are captured before the first write
        (None = file did not exist → restore deletes it, restore-parity)."""
        by_file: dict[str, list[PatchBlock]] = {}
        known_files = {p.file_path for p in patches if p.file_path}
        universe = known_files | (candidate_files or set())
        for patch in patches:
            target = patch.file_path
            if not target:
                target = self._disambiguate_target(patch, universe, repo_root)
                if target is None:
                    if len(known_files) == 1:
                        target = next(iter(known_files))
                    elif len(universe) == 1:
                        target = next(iter(universe))
                    else:
                        raise PatchApplicationError(
                            "patch has no file path and target is ambiguous"
                        )
            by_file.setdefault(target, []).append(patch)

        for rel, file_patches in by_file.items():
            path = _safe_path(repo_root, rel)
            if rel not in originals:
                try:
                    originals[rel] = path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    originals[rel] = None
                except (OSError, UnicodeDecodeError) as e:
                    raise PatchApplicationError(f"cannot read {rel}: {e}") from e
            if originals[rel] is None:
                # Create-file semantics: concatenated replace blocks.
                if any(p.search_block.strip() != "" for p in file_patches):
                    raise PatchApplicationError(
                        f"{rel} does not exist; new files need empty search blocks"
                    )
                new_content = "\n".join(p.replace_block for p in file_patches)
            else:
                new_content = apply_all(originals[rel] or "", file_patches)
            path.write_text(new_content, encoding="utf-8")

    @staticmethod
    def _disambiguate_target(
        patch: PatchBlock, candidates: set[str], repo_root: str
    ) -> str | None:
        """Attribute a path-less patch by matching its search block against
        candidate file contents; exactly one match wins, else None."""
        from janus.patcher.engine import apply_patch

        contents: dict[str, str] = {}
        matches = []
        for rel in sorted(candidates):
            try:
                if rel not in contents:
                    contents[rel] = _safe_path(repo_root, rel).read_text(encoding="utf-8")
                apply_patch(contents[rel], patch)
            except (PatchApplicationError, OSError, UnicodeDecodeError):
                continue
            matches.append(rel)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _restore(originals: dict[str, str | None], repo_root: str) -> None:
        for rel, content in originals.items():
            if content is None:
                _safe_path(repo_root, rel).unlink(missing_ok=True)
            else:
                _safe_path(repo_root, rel).write_text(content, encoding="utf-8")
