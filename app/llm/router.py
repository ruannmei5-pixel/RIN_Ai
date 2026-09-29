"""
router.py

TAHAP 3 — AI PROVIDER ROUTER.

Titik tunggal pemilihan provider (Ollama / NVIDIA / OpenRouter) +
fallback. Tidak ada seleksi provider yang tersebar di file lain:
`app/core/assistant.py` dan `app/api/routes.py` SELALU lewat
`AIProviderRouter` ini untuk mendapatkan balasan AI.

    User
     ↓
    RIN Assistant
     ↓
    AI Provider Router   <-- file ini
     ├── NVIDIA AI
     ├── OpenRouter
     └── Ollama
           ↓
       selected model

FALLBACK:
    Jika provider yang diminta gagal (timeout/unavailable/API error/
    auth error) DAN fallback diaktifkan (config.ai.fallback_enabled),
    router mencoba `config.ai.fallback_provider`. Kegagalan ini TIDAK
    disembunyikan dari caller: setiap hasil chat membawa `ChatOutcome`
    yang menyatakan provider_used / provider_requested / fallback_used,
    supaya frontend bisa menampilkan mis. "Using Ollama fallback" alih-
    alih diam-diam mengganti provider tanpa pemberitahuan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from app.core.config import AppConfig
from app.core.logger import get_logger
from app.llm.base import AIProvider, ChatMessage, ProviderError
from app.llm.ollama_client import OllamaClient
from app.llm.providers import NvidiaProvider, OllamaProvider, OpenRouterProvider

logger = get_logger()

PROVIDER_IDS: Tuple[str, ...] = ("ollama", "nvidia", "openrouter")


@dataclass
class ChatOutcome:
    """Metadata non-rahasia tentang provider mana yang sebenarnya menjawab."""

    provider_used: str
    provider_requested: str
    fallback_used: bool


class AIProviderRouter:
    """
    Membangun dan menyimpan instance dari ketiga provider, lalu
    menyediakan chat()/chat_stream() dengan fallback yang aman.
    """

    def __init__(self, config: AppConfig, ollama_client: Optional[OllamaClient] = None) -> None:
        self.config = config

        # Ollama: pakai instance yang sama dengan Assistant jika
        # diberikan (supaya tidak ada dua koneksi Ollama terpisah untuk
        # hal yang sama); kalau tidak, buat baru dari config.
        shared_ollama_client = ollama_client or OllamaClient(
            host=config.ollama.host,
            model=config.ollama.model,
            timeout_seconds=config.ollama.timeout_seconds,
        )

        self._providers: Dict[str, AIProvider] = {
            "ollama": OllamaProvider(shared_ollama_client),
            "nvidia": NvidiaProvider(
                api_key=config.nvidia.api_key,
                base_url=config.nvidia.base_url,
                model=config.nvidia.model,
            ),
            "openrouter": OpenRouterProvider(
                api_key=config.openrouter.api_key,
                base_url=config.openrouter.base_url,
                model=config.openrouter.model,
            ),
        }

    # --------------------------------------------------------------
    # LOOKUP
    # --------------------------------------------------------------

    def get(self, provider_id: str) -> Optional[AIProvider]:
        return self._providers.get((provider_id or "").strip().lower())

    def all_providers(self) -> Dict[str, AIProvider]:
        return dict(self._providers)

    def resolve(self, requested: Optional[str]) -> str:
        """
        Menentukan provider id yang valid untuk dipakai: `requested`
        jika valid, kalau tidak fallback ke config.ai.provider, kalau
        itu pun tidak valid fallback ke "ollama" (never crash on a bad
        provider id).
        """
        candidate = (requested or self.config.ai.provider or "ollama").strip().lower()
        if candidate in self._providers:
            return candidate
        logger.warning(
            "AI_ROUTER: provider %r tidak dikenal, memakai 'ollama'.",
            candidate,
        )
        return "ollama"

    @property
    def default_provider_id(self) -> str:
        return self.resolve(self.config.ai.provider)

    # --------------------------------------------------------------
    # CHAT (non-streaming)
    # --------------------------------------------------------------

    def chat(
        self,
        messages: List[ChatMessage],
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[str, ChatOutcome]:
        requested = self.resolve(provider_id)
        provider = self._providers[requested]

        try:
            reply = provider.chat(messages, model=model)
            return reply, ChatOutcome(requested, requested, False)
        except ProviderError as exc:
            logger.warning(
                "AI_ROUTER: provider=%s gagal (%s), cek fallback.",
                requested,
                exc,
            )
            fallback_id = self._resolve_fallback(requested)
            if fallback_id is None:
                raise
            fallback_provider = self._providers[fallback_id]
            reply = fallback_provider.chat(messages)
            logger.info(
                "AI_ROUTER: fallback dipakai. requested=%s used=%s",
                requested,
                fallback_id,
            )
            return reply, ChatOutcome(fallback_id, requested, True)

    # --------------------------------------------------------------
    # CHAT (streaming)
    # --------------------------------------------------------------

    def chat_stream(
        self,
        messages: List[ChatMessage],
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[Iterator[str], ChatOutcome]:
        """
        Mengembalikan (generator_chunk, outcome). `outcome` SUDAH final
        saat method ini return (bukan belakangan di tengah stream),
        karena chunk pertama sudah "ditarik" (mirip pola existing di
        app/api/routes.py::chat_stream) untuk memastikan error provider
        (koneksi/auth/model) diketahui SEBELUM stream benar-benar
        dibuka ke client.
        """
        requested = self.resolve(provider_id)
        provider = self._providers[requested]

        try:
            generator = provider.chat_stream(messages, model=model)
            first_chunk: Optional[str] = next(generator, None)
        except ProviderError as exc:
            logger.warning(
                "AI_ROUTER: provider=%s gagal saat streaming (%s), cek fallback.",
                requested,
                exc,
            )
            fallback_id = self._resolve_fallback(requested)
            if fallback_id is None:
                raise
            fallback_provider = self._providers[fallback_id]
            fb_generator = fallback_provider.chat_stream(messages)
            fb_first_chunk = next(fb_generator, None)
            logger.info(
                "AI_ROUTER: fallback dipakai (stream). requested=%s used=%s",
                requested,
                fallback_id,
            )

            def _fallback_stream() -> Iterator[str]:
                if fb_first_chunk is not None:
                    yield fb_first_chunk
                yield from fb_generator

            return _fallback_stream(), ChatOutcome(fallback_id, requested, True)

        def _stream() -> Iterator[str]:
            if first_chunk is not None:
                yield first_chunk
            yield from generator

        return _stream(), ChatOutcome(requested, requested, False)

    # --------------------------------------------------------------
    # FALLBACK RESOLUTION
    # --------------------------------------------------------------

    def _resolve_fallback(self, requested: str) -> Optional[str]:
        if not self.config.ai.fallback_enabled:
            return None

        fallback_id = (self.config.ai.fallback_provider or "ollama").strip().lower()

        if fallback_id not in self._providers:
            logger.warning(
                "AI_ROUTER: fallback provider %r tidak dikenal.",
                fallback_id,
            )
            return None

        if fallback_id == requested:
            # Jangan fallback ke provider yang sama (tidak ada gunanya).
            return None

        return fallback_id
