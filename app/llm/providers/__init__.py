"""
app/llm/providers

TAHAP 3 — Implementasi konkret AIProvider:

- OllamaProvider     -> app/llm/providers/ollama_provider.py
- NvidiaProvider     -> app/llm/providers/nvidia_provider.py
- OpenRouterProvider -> app/llm/providers/openrouter_provider.py

Lihat app/llm/base.py untuk interface AIProvider, dan
app/llm/router.py untuk AI Provider Router (pemilihan + fallback).
"""

from __future__ import annotations

from app.llm.providers.nvidia_provider import NvidiaProvider
from app.llm.providers.ollama_provider import OllamaProvider
from app.llm.providers.openrouter_provider import OpenRouterProvider

__all__ = ["NvidiaProvider", "OllamaProvider", "OpenRouterProvider"]
