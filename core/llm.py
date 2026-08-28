"""Shared Groq LLM factory for summarization, extraction, and RAG."""

from __future__ import annotations

import os

from langchain_groq import ChatGroq

# Free-tier Llama models were shut down Aug 2026; gpt-oss is the current default.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


def get_llm(*, temperature: float = 0.2) -> ChatGroq:
    """Return a ChatGroq client configured for clean text answers.

    gpt-oss models are reasoning models. Without ``reasoning_format="hidden"``,
    LangChain's StrOutputParser can receive empty/noisy content and summaries
    / action items look broken even when the API call succeeds.
    """
    model = (os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()
    api_key = (os.getenv("GROQ_API_KEY") or "").strip() or None

    kwargs: dict = {
        "model": model,
        "groq_api_key": api_key,
        "temperature": temperature,
    }

    # Only set reasoning_format for models that support it (gpt-oss / known reasoners).
    if "gpt-oss" in model.lower() or "qwen" in model.lower() or "deepseek" in model.lower():
        kwargs["reasoning_format"] = "hidden"

    return ChatGroq(**kwargs)
