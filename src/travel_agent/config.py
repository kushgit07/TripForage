"""Centralized, typed application configuration.

Everything the app reads from the environment goes through this module instead of
scattered `os.environ[...]` calls. That gives us: one place to see every required
setting, validation at startup (fail fast with a clear error instead of a KeyError
three calls deep), and easy overriding in tests.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM provider: "groq" or "nvidia". Both have free tiers; see README for tradeoffs.
    llm_provider: str = "groq"

    # Groq (free tier) — llama-3.3-70b-versatile was deprecated by Groq on 2026-06-17;
    # use openai/gpt-oss-120b or qwen/qwen3.6-27b instead. Check console.groq.com/docs/models
    # for the current list before relying on any specific name.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # NVIDIA NIM (free tier via build.nvidia.com) — OpenAI-compatible endpoint, so we reuse
    # ChatOpenAI with a custom base_url rather than adding another SDK dependency.
    # NVIDIA's free tier terms restrict it to development/testing/research/evaluation, not
    # serving real end-user production traffic — same caveat applies to Groq's free tier.
    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.3-70b-instruct"  # verify current slug at build.nvidia.com
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # Duffel flight/hotel search (migrated off Amadeus, whose Self-Service portal
    # was shut down 2026-07-17). Duffel doesn't use a separate sandbox base URL —
    # test vs. live mode is determined by the key itself: a "duffel_test_..." key
    # only returns simulated data, a "duffel_live_..." key hits real suppliers.
    duffel_api_key: str = ""
    duffel_base_url: str = "https://api.duffel.com"
    duffel_api_version: str = "v2"

    # Resend email (free tier: 100 emails/day, 3,000/month, no card)
    resend_api_key: str = ""

    # LangSmith tracing (optional)
    langchain_api_key: str = ""
    langchain_tracing_v2: bool = False
    langchain_project: str = "ai-travel-agent"

    # App behaviour
    max_tool_iterations: int = 6
    search_cache_ttl_seconds: int = 900
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _check_llm_provider_key(self) -> Settings:
        if self.llm_provider not in ("groq", "nvidia"):
            raise ValueError(f"Unsupported LLM_PROVIDER '{self.llm_provider}'. Use 'groq' or 'nvidia'.")
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("LLM_PROVIDER=groq requires GROQ_API_KEY to be set.")
        if self.llm_provider == "nvidia" and not self.nvidia_api_key:
            raise ValueError("LLM_PROVIDER=nvidia requires NVIDIA_API_KEY to be set.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process. Tests can bypass this with dependency overrides."""
    return Settings()  # type: ignore[call-arg]  # values come from env/.env
