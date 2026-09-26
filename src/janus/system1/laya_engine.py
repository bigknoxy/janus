"""Laya-backed System 1.

Laya is a non-autoregressive decision model: typed questions in, calibrated
answers out, one forward pass. It imports lazily — the 808MB checkpoint and
the `laya` package are only touched when this engine is actually constructed
(`pip install janus-code[laya]`).
"""

from typing import Any

from janus.core.config import JanusSettings
from janus.core.types import IntentType, System1Decision
from janus.system1.base import enforce_confidence_gate
from janus.system1.schemas import (
    DEFAULT_MARGIN_FLOOR,
    file_relevance_question,
    intent_questions,
)


class LayaDecisionEngine:
    """DecisionEngineProtocol implementation over a local Laya Router."""

    def __init__(self, settings: JanusSettings | None = None) -> None:
        self._settings = settings or JanusSettings()
        # In-process mode: single checkpoint direct-load, NOT
        # Router(preload=True) — preload keeps 2 checkpoints resident
        # (~1.5GB) and OOMs the 14GiB laptop alongside the llama servers.
        self._agent: Any | None = None
        if not self._settings.s1_serve_url:
            try:
                import laya
            except ImportError as e:  # surfaced at construction, not mid-run
                raise RuntimeError(
                    "laya is not installed; run `pip install janus-code[laya]`"
                ) from e
            self._agent = laya.load(
                self._settings.s1_checkpoint,
                subfolder=(self._settings.s1_subfolder or None),
            )

    def _predict_http(self, state: dict, questions: dict) -> dict[str, Any]:
        """laya-serve backend (Jev-compatible /v1/systemone). Same schema,
        same decision assembler — the protocol seam is real."""
        import httpx

        url = f"{self._settings.s1_serve_url.rstrip('/')}/v1/systemone"
        body: dict[str, Any] = {"state": state, "questions": questions}
        if self._settings.s1_subfolder:
            body["model"] = self._settings.s1_subfolder
        try:
            resp = httpx.post(url, json=body, timeout=120.0)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except (httpx.HTTPError, ValueError) as e:
            raise RuntimeError(f"laya-serve backend error: {e}") from e

    def evaluate(self, user_prompt: str, repo_summary: str) -> System1Decision:
        state = {"request": user_prompt, "repository": repo_summary}

        questions: dict[str, dict] = intent_questions()
        # Candidate files = one noul question per repo_map line that looks
        # like a path, so file selection stays batchable and unbounded.
        # The skeleton signature goes inside each question: path-only
        # relevance starved the noul head on generic names (probe 2026-09-24).
        candidates = _candidate_files(repo_summary)
        # Deterministic-first targeting: a path named verbatim in the
        # prompt is the dominant signal and needs no model call. (Live
        # probe 2026-09-24: relevance nouls saturate near 0.5 for all
        # files — noise, not signal.)
        prompt_norm = " ".join(user_prompt.split())
        pinned = [
            p
            for p in candidates
            if p in prompt_norm or ("/" in p and p.split("/")[-1] in prompt_norm)
        ]
        if not pinned:
            for path in candidates:
                questions[f"file:{path}"] = file_relevance_question(
                    path, candidates[path]
                )

        if self._agent is not None:
            result: dict[str, Any] = self._agent.predict(state, questions)
        else:
            result = self._predict_http(state, questions)
        answers = result.get("answers", {})

        scores = {
            key[len("intent:"):]: float(ans.get("noul", 0.0))
            for key, ans in answers.items()
            if key.startswith("intent:")
        }
        try:
            ranked_intents = sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]
            intent = IntentType(ranked_intents[0])
        except (IndexError, ValueError):
            intent, scores, ranked_intents = IntentType.UNCLEAR_ESCALATE, {}, []
        confidence = min(max(scores.get(intent, 0.0), 0.0), 1.0)
        margin = (
            scores[ranked_intents[0]] - scores[ranked_intents[1]]
            if len(ranked_intents) >= 2
            else 1.0
        )

        if pinned:
            target_files = pinned[:3]
        else:
            target_files = [
                key[len("file:"):]
                for key, ans in answers.items()
                if key.startswith("file:") and ans.get("noul", 0.0) >= 0.6
            ][:3]

        # Dogfood 2026-09-25: vague prompts hedge all nouls near 0.5 with
        # margins that overlap clear prompts — no probability gate separates
        # them, and file-relevance nouls also spike on vague asks. Rule:
        # a write request with NO literal anchor (no path, no symbol name
        # from the repo map) escalates deterministically.
        # Rerun evidence day-2: 'it's broken, make it work' assigned noul
        # 0.72 to mod.py and patched it — anchors only, never nouls alone.
        symbol_pins = _mentioned_repo_symbols(user_prompt, repo_summary)
        if intent == IntentType.CODE_MODIFICATION and not (pinned or symbol_pins):
            intent = IntentType.UNCLEAR_ESCALATE
        if symbol_pins and intent == IntentType.CODE_MODIFICATION:
            extra_files = _files_for_symbols(symbol_pins, repo_summary)
            target_files = list(dict.fromkeys(pinned + extra_files + target_files))[:3]

        decision = System1Decision(
            intent=intent,
            confidence=confidence,
            margin=margin,
            target_files=target_files,
            anchored=bool(pinned or symbol_pins),
            target_symbols=symbol_pins,
            micro_instruction=" ".join(user_prompt.split()),
            requires_s2=intent == IntentType.CODE_MODIFICATION,
        )
        return enforce_confidence_gate(
            decision,
            self._settings.confidence_threshold,
            margin_floor=getattr(self._settings, "s1_margin_floor", DEFAULT_MARGIN_FLOOR),
            modify_margin_floor=getattr(self._settings, "s1_modify_margin_floor", 0.04),
        )


_SYMBOL_DEF = None


def _mentioned_repo_symbols(prompt: str, repo_summary: str) -> list[str]:
    """Symbols defined in the repo map that are named verbatim in the
    prompt (word-boundary). The deterministic second anchor besides paths."""
    import re

    pinned: list[str] = []
    for line in repo_summary.splitlines():
        for m in re.finditer(r"\b(?:def|class|function)\s+([A-Za-z_]\w*)", line):
            name = m.group(1)
            if len(name) >= 3 and re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", prompt):
                pinned.append(name)
    return pinned


def _files_for_symbols(symbols: list[str], repo_summary: str) -> list[str]:
    """Files whose repo_map line declares one of the pinned symbols."""
    files: list[str] = []
    for line in repo_summary.splitlines():
        token = line.strip().split(" ", 1)[0]
        if "/" not in token and "." not in token:
            continue  # signature lines (def/class heads) are not files
        if any(
            f"def {s}(" in line or f"class {s}" in line or f"function {s}" in line
            for s in symbols
        ):
            files.append(token)
    return files


def _candidate_files(repo_summary: str) -> dict[str, str]:
    """Map path-like tokens from a repo_map summary to their signature lines."""
    paths: dict[str, str] = {}
    for line in repo_summary.splitlines():
        stripped = line.strip()
        token = stripped.split(" ", 1)[0]
        if "/" in token or "." in token:
            paths[token] = stripped[len(token):].strip()[:120]
    return dict(list(paths.items())[:64])  # question budget guard


