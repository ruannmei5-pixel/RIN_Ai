"""
ollama_provider.py

TAHAP 3 — Adapter yang membungkus `OllamaClient` (app/llm/ollama_client.py,
TIDAK diubah strukturnya) menjadi `AIProvider` yang seragam dengan
NvidiaProvider.

Ollama adalah local AI provider dan FALLBACK/BACKUP untuk NVIDIA AI
(NVIDIA = provider utama, lihat app/llm/router.py). Semua perilaku OllamaClient yang sudah ada (streaming,
thinking-filter Qwen, error handling) TIDAK disentuh — adapter ini
hanya menerjemahkan exception OllamaError -> ProviderError yang
dipakai lintas provider.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

import httpx

from app.core.logger import get_logger
from app.llm.base import (
    AIProvider,
    ChatMessage,
    ProviderConnectionError,
    ProviderHealth,
    ProviderModelNotFoundError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.llm.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)

logger = get_logger()


class OllamaProvider(AIProvider):
    id = "ollama"
    display_name = "Ollama"

    def __init__(self, client: OllamaClient) -> None:
        # Dipakai ulang: instance OllamaClient yang SAMA yang juga
        # dipakai Assistant untuk system_info routing / search
        # classifier, supaya tidak ada dua koneksi Ollama terpisah.
        self._client = client

    # --------------------------------------------------------------
    # CHAT
    # --------------------------------------------------------------

    def chat(self, messages: List[ChatMessage], model: Optional[str] = None) -> str:
        try:
            return self._client.chat(messages, model=model)
        except OllamaModelNotFoundError as exc:
            raise ProviderModelNotFoundError(str(exc)) from exc
        except OllamaConnectionError as exc:
            raise ProviderConnectionError(str(exc)) from exc
        except OllamaTimeoutError as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except OllamaResponseError as exc:
            raise ProviderResponseError(str(exc)) from exc
        except OllamaError as exc:
            # OllamaError generik (mis. dari _raise_generic) tetap harus
            # menjadi ProviderError supaya router/routes memperlakukannya
            # secara seragam.
            raise ProviderResponseError(str(exc)) from exc

    def chat_stream(self, messages: List[ChatMessage], model: Optional[str] = None) -> Iterator[str]:
        try:
            for chunk in self._client.chat_stream(messages, model=model):
                yield chunk
        except OllamaModelNotFoundError as exc:
            raise ProviderModelNotFoundError(str(exc)) from exc
        except OllamaConnectionError as exc:
            raise ProviderConnectionError(str(exc)) from exc
        except OllamaTimeoutError as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except OllamaResponseError as exc:
            raise ProviderResponseError(str(exc)) from exc
        except OllamaError as exc:
            raise ProviderResponseError(str(exc)) from exc

    # --------------------------------------------------------------
    # MODELS / HEALTH
    # --------------------------------------------------------------

    def is_configured(self) -> bool:
        # Ollama local selalu dianggap "configured" (host+model punya
        # default di config.json) — beda dari NVIDIA yang
        # butuh API key eksplisit.
        return bool(self._client.host) and bool(self._client.model)

    @property
    def active_model(self) -> str:
        return self._client.model

    def get_models(self) -> List[str]:
        """
        Dynamic model discovery via `GET {host}/api/tags` (endpoint
        Ollama existing). Panggilan HTTP terpisah, ringan, dengan timeout
        pendek supaya tidak memblokir UI Settings jika Ollama lambat/mati.
        """
        try:
            response = httpx.get(
                f"{self._client.host}/api/tags",
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            return [
                str(item.get("name") or item.get("model") or "").strip()
                for item in models
                if isinstance(item, dict) and (item.get("name") or item.get("model"))
            ]
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.warning("OLLAMA_PROVIDER: gagal mengambil daftar model: %s", exc)
            return []

    def health_check(self) -> ProviderHealth:
        try:
            response = httpx.get(
                f"{self._client.host}/api/tags",
                timeout=5,
            )
            response.raise_for_status()
            return ProviderHealth(
                configured=True,
                available=True,
                detail=f"{self._client.model} @ {self._client.host}",
            )
        except Exception:
            return ProviderHealth(
                configured=True,
                available=False,
                detail=f"Ollama tidak dapat dihubungi di {self._client.host}.",
            )
