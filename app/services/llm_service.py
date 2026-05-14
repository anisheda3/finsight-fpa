from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings


async def generate_json_with_llm(
    prompt: str,
    system_prompt: str = "You are a careful financial AI assistant. Respond only with valid JSON.",
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> dict[str, Any]:
    """
    Central LLM JSON generation wrapper.

    Currently supports Gemini via google-genai.
    """

    settings = get_settings()

    if settings.llm_provider.lower() != "gemini":
        raise ValueError(
            f"Only Gemini is supported. LLM_PROVIDER is set to {settings.llm_provider}"
        )

    return await generate_json_with_gemini(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def generate_text_with_llm(
    prompt: str,
    system_prompt: str = "You are a helpful financial AI assistant.",
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> str:
    settings = get_settings()

    if settings.llm_provider.lower() != "gemini":
        raise ValueError(
            f"Only Gemini is supported. LLM_PROVIDER is set to {settings.llm_provider}"
        )

    return await generate_text_with_gemini(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def generate_text_with_gemini(
    prompt: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    from google import genai
    from google.genai import types

    settings = get_settings()

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is missing")

    client = genai.Client(api_key=settings.gemini_api_key)

    response = client.models.generate_content(
        model=settings.llm_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )

    return response.text or ""


async def generate_json_with_gemini(
    prompt: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    text = await generate_text_with_gemini(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    cleaned = strip_json_fences(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting JSON object from surrounding text.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def strip_json_fences(text: str) -> str:
    raw = text.strip()

    if raw.startswith("```json"):
        raw = raw.removeprefix("```json").strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```").strip()
    if raw.endswith("```"):
        raw = raw.removesuffix("```").strip()

    return raw