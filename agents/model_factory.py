from __future__ import annotations

from app.core.config import get_settings


def get_agno_model():
    settings = get_settings()

    if settings.llm_provider.lower() != "gemini":
        raise ValueError(
            f"Only Gemini is supported. LLM_PROVIDER is set to {settings.llm_provider}"
        )

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is missing in .env")

    from agno.models.google import Gemini

    return Gemini(
        id=settings.llm_model,
        api_key=settings.gemini_api_key,
    )
