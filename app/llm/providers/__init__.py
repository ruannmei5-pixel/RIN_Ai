"""
app/llm/providers

Implementasi konkret AIProvider:

- NvidiaProvider -> app/llm/providers/nvidia_provider.py   (PROVIDER UTAMA)
- OllamaProvider -> app/llm/providers/ollama_provider.py   (FALLBACK / lokal)

NvidiaProvider dibangun di atas OpenAICompatibleProvider
(app/llm/providers/openai_compatible.py).

Lihat app/llm/base.py untuk interface AIProvider, dan
app/llm/router.py untuk AI Provider Router (pemilihan + fallback).
"""

from __future__ import annotations

from app.llm.providers.nvidia_provider import NvidiaProvider
from app.llm.providers.ollama_provider import OllamaProvider

__all__ = ["NvidiaProvider", "OllamaProvider"]