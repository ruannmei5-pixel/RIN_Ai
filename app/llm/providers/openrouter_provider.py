"""
openrouter_provider.py

TAHAP 3 — Provider untuk OpenRouter (https://openrouter.ai), yang
kompatibel dengan OpenAI-style chat completions dan mendukung banyak
model dari berbagai vendor lewat satu API key.

Environment variables (lihat .env.example, app/core/config.py):

    OPENROUTER_API_KEY=
    OPENROUTER_BASE_URL= (default: https://openrouter.ai/api/v1)
    OPENROUTER_MODEL=

Model HARUS configurable (bukan dikunci ke satu model) — lihat
app/api/routes.py: GET /api/ai/models?provider=openrouter, dan
Settings model dropdown di frontend.

API key HANYA dibaca dari environment (app/core/config.py), TIDAK
PERNAH di-hardcode di sini / dikirim ke browser.
"""

from __future__ import annotations

from app.llm.providers.openai_compatible import OpenAICompatibleProvider

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatibleProvider):
    id = "openrouter"
    display_name = "OpenRouter"

    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: int = 60) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or DEFAULT_OPENROUTER_BASE_URL,
            model=model,
            timeout_seconds=timeout_seconds,
            # Header opsional yang direkomendasikan OpenRouter untuk
            # atribusi aplikasi di dashboard mereka. Tidak wajib, dan
            # TIDAK berisi data rahasia apa pun.
            extra_headers={
                "HTTP-Referer": "https://github.com/rin-assistant",
                "X-Title": "RIN Assistant",
            },
        )
