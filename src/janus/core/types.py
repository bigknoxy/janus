"""Shared Pydantic domain types — the single source of truth for every
intermediate representation flowing through Janus (DRY)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class IntentType(StrEnum):
    DIRECT_ACTION = "direct_action"          # Run command, git op, etc.
    CODE_MODIFICATION = "code_modification"  # Refactor, fix, write function
    EXPLANATION = "explanation"              # Read-only query
    UNCLEAR_ESCALATE = "escalate"            # Low confidence / ambiguous


class System1Decision(BaseModel):
    """The gate's typed verdict. Produced by the DecisionEngineProtocol."""

    intent: IntentType
    confidence: float = Field(..., ge=0.0, le=1.0)
    margin: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="top1 - top2 probability gap; the real ambiguity signal",
    )
    target_files: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(
        default_factory=list, description="Target function or class names"
    )
    micro_instruction: str = Field(
        ..., description="Single clean sentence stripped of fluff"
    )
    requires_s2: bool


class PatchBlock(BaseModel):
    file_path: str
    search_block: str
    replace_block: str


class VerificationResult(BaseModel):
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
