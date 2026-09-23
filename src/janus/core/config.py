"""Runtime configuration, sourced from env vars (prefix JANUS_) or a .env file.

Endpoints are never hardcoded; the local-laptop hosts live in env config.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class JanusSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JANUS_", env_file=".env", extra="ignore")

    # --- System 1 (Laya) ---
    s1_backend: str = Field(
        default="laya", description="Decision engine backend: 'laya' | 'mock'"
    )
    s1_checkpoint: str = "convaiinnovations/laya"
    s1_device: str = Field(default="cpu", description="cpu | cuda")
    s1_preload: bool = True
    confidence_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Below this, escalate to the user"
    )

    # --- System 2 (local LLM, OpenAI-compatible) ---
    s2_base_url: str = Field(
        default="http://localhost:8080/v1",
        description="OpenAI-compatible endpoint for the generative model",
    )
    s2_model: str = "qwen3-4b"
    s2_temperature: float = Field(default=0.0, ge=0.0)
    s2_max_tokens: int = Field(default=2048, gt=0)
    s2_timeout_s: float = Field(default=300.0, gt=0.0)

    # --- Verification ---
    verify_command: str = Field(
        default="pytest -q", description="Shell command used to verify patches"
    )
    verify_timeout_s: float = Field(default=120.0, gt=0.0)
    max_repair_attempts: int = Field(default=1, ge=0, le=3)
