"""
nvidia_provider.py

TAHAP 3 — Provider untuk NVIDIA AI (NVIDIA API Catalog / NIM), yang
kompatibel dengan OpenAI-style chat completions.

Environment variables (lihat .env.example, app/core/config.py):

    NVIDIA_API_KEY=
    NVIDIA_BASE_URL=      (default: https://integrate.api.nvidia.com/v1)
    NVIDIA_MODEL=

API key HANYA dibaca dari environment (app/core/config.py), TIDAK
PERNAH di-hardcode di sini.
"""

from __future__ import annotations

from app.llm.providers.openai_compatible import OpenAICompatibleProvider

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(OpenAICompatibleProvider):
    id = "nvidia"
    display_name = "NVIDIA AI"

    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: int = 60) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or DEFAULT_NVIDIA_BASE_URL,
            model=model,
            timeout_seconds=timeout_seconds,
        )
