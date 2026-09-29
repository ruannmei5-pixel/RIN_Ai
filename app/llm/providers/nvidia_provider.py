"""
nvidia_provider.py

Provider UTAMA RIN: NVIDIA AI (NVIDIA API Catalog / NIM), yang
kompatibel dengan OpenAI-style chat completions. Ollama hanya dipakai
sebagai fallback per-request (lihat app/llm/router.py).

Environment variables (lihat .env.example, app/core/config.py):

    NVIDIA_API_KEY=
    NVIDIA_BASE_URL=      (default: https://integrate.api.nvidia.com/v1)
    NVIDIA_MODEL=
    NVIDIA_TIMEOUT_SECONDS=            (default 25, batas tunggu token pertama)
    NVIDIA_CONNECT_TIMEOUT_SECONDS=    (default 5)

API key HANYA dibaca dari environment (app/core/config.py), TIDAK
PERNAH di-hardcode di sini.
"""

from __future__ import annotations

from typing import Any, Optional

from app.llm.providers.openai_compatible import OpenAICompatibleProvider

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(OpenAICompatibleProvider):
    id = "nvidia"
    display_name = "NVIDIA AI"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 25.0,
        connect_timeout_seconds: float = 5.0,
        transport: Optional[Any] = None,
    ) -> None:
        # Default 25 detik (bukan 60): NVIDIA adalah provider cloud yang
        # biasanya mengirim token pertama dalam hitungan detik. Jika lebih
        # lama dari ini, lebih baik segera fallback ke Ollama (lihat
        # app/llm/router.py) daripada membuat user menunggu.
        super().__init__(
            api_key=api_key,
            base_url=base_url or DEFAULT_NVIDIA_BASE_URL,
            model=model,
            timeout_seconds=timeout_seconds,
            connect_timeout_seconds=connect_timeout_seconds,
            transport=transport,  # hanya untuk tes offline (httpx.MockTransport)
        )
