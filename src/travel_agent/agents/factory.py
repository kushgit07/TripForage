"""Wires concrete dependencies (LLM, Duffel client, Resend) into a TravelAgent.

Kept separate from graph.py so graph.py itself has zero knowledge of which LLM
provider or which travel-data API is in use — swapping providers only touches
this file.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from travel_agent.agents.graph import TravelAgent
from travel_agent.config import Settings
from travel_agent.services import DuffelClient, EmailService, SearchCache
from travel_agent.tools import build_flights_tool, build_hotels_tool


def _build_llm(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0.2)

    if settings.llm_provider == "nvidia":
        # NVIDIA's build.nvidia.com endpoint is OpenAI-compatible, so plain ChatOpenAI
        # pointed at a different base_url works — no extra SDK dependency needed.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.nvidia_model,
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            temperature=0.2,
        )

    # Settings validation should prevent this, but fail loudly if it's ever bypassed.
    raise ValueError(f"Unsupported LLM_PROVIDER '{settings.llm_provider}'.")


def build_agent(settings: Settings) -> TravelAgent:
    llm = _build_llm(settings)

    duffel_client = DuffelClient(
        api_key=settings.duffel_api_key,
        base_url=settings.duffel_base_url,
        api_version=settings.duffel_api_version,
    )
    cache = SearchCache(ttl_seconds=settings.search_cache_ttl_seconds)

    tools = [
        build_flights_tool(duffel_client, cache),
        build_hotels_tool(duffel_client, cache),
    ]
    email_service = EmailService(api_key=settings.resend_api_key)

    return TravelAgent(llm=llm, tools=tools, email_service=email_service, max_iterations=settings.max_tool_iterations)
