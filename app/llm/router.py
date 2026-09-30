"""
router.py

TAHAP 3 — AI PROVIDER ROUTER.

Titik tunggal pemilihan provider (NVIDIA AI = utama, Ollama = fallback).

    User -> RIN Assistant -> AI Provider Router -> NVIDIA AI (dicoba pertama)
                                                     |-- berhasil -> response
                                                     |-- gagal    -> Ollama -> response

FALLBACK:
    Jika provider yang diminta gagal DAN fallback diaktifkan
    (config.ai.fallback_enabled), router mencoba config.ai.fallback_provider
    HANYA untuk request itu. config.ai.provider tidak pernah diubah.

COOLDOWN (opsional, env PROVIDER_COOLDOWN_SECONDS, default 0 = mati):
    Setelah provider utama gagal karena timeout/koneksi/unavailable/auth,
    provider itu dilewati selama N detik dan request langsung ke fallback.
    Setelah itu provider utama dicoba lagi.

Setiap hasil chat membawa ChatOutcome (provider_used / provider_requested /
fallback_used) supaya fallback tidak pernah terjadi diam-diam.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from app.core.config import AppConfig
from app.core.logger import get_logger
from app.llm.base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.llm.ollama_client import OllamaClient
from app.llm.providers import NvidiaProvider, OllamaProvider

logger = get_logger()

PROVIDER_IDS: Tuple[str, ...] = ("nvidia", "ollama")


@dataclass
class ChatOutcome:
    """Metadata non-rahasia tentang provider mana yang sebenarnya menjawab."""

    provider_used: str
    provider_requested: str
    fallback_used: bool


class AIProviderRouter:
    """
    Membangun dan menyimpan instance provider (NVIDIA & Ollama), lalu
    menyediakan chat()/chat_stream() dengan fallback yang aman.
    """

    def __init__(self, config: AppConfig, ollama_client: Optional[OllamaClient] = None) -> None:
        self.config = config

        shared_ollama_client = ollama_client or OllamaClient(
            host=config.ollama.host,
            model=config.ollama.model,
            timeout_seconds=config.ollama.timeout_seconds,
        )

        self._providers: Dict[str, AIProvider] = {
            "nvidia": NvidiaProvider(
                api_key=config.nvidia.api_key,
                base_url=config.nvidia.base_url,
                model=config.nvidia.model,
                timeout_seconds=config.nvidia.timeout_seconds,
                connect_timeout_seconds=config.nvidia.connect_timeout_seconds,
            ),
            "ollama": OllamaProvider(shared_ollama_client),
        }

        # Cooldown (0 = mati).
        try:
            self._cooldown_seconds = float(os.getenv("PROVIDER_COOLDOWN_SECONDS", "0") or 0)
        except ValueError:
            self._cooldown_seconds = 0.0
        self._skip_until: Dict[str, float] = {}

    # --------------------------------------------------------------
    # LOOKUP
    # --------------------------------------------------------------

    def get(self, provider_id: str) -> Optional[AIProvider]:
        return self._providers.get((provider_id or "").strip().lower())

    def all_providers(self) -> Dict[str, AIProvider]:
        return dict(self._providers)

    def resolve(self, requested: Optional[str]) -> str:
        """
        Menentukan provider id yang valid: `requested` jika valid, kalau
        tidak pakai config.ai.provider (NVIDIA), kalau itu pun tidak
        valid "nvidia".
        """
        candidate = (requested or "").strip().lower()
        if candidate in self._providers:
            return candidate

        if candidate:
            logger.warning(
                "AI_ROUTER: provider %r tidak dikenal, memakai provider utama.",
                candidate,
            )

        default = (self.config.ai.provider or "").strip().lower()
        if default in self._providers:
            return default
        return "nvidia"

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
        skip = self._should_skip(requested)

        try:
            if skip:
                raise ProviderUnavailableError(f"{requested} sedang cooldown.")
            reply = provider.chat(messages, model=model)
            return reply, ChatOutcome(requested, requested, False)
        except ProviderError as exc:
            if not skip:
                self._mark_failed(requested, exc)
            logger.warning(
                "AI_ROUTER: provider=%s gagal (%s), cek fallback.",
                requested,
                exc,
            )
            fallback_id = self._resolve_fallback(requested)
            if fallback_id is None:
                raise
            fallback_provider = self._providers[fallback_id]
            try:
                reply = fallback_provider.chat(messages)
            except ProviderError as fb_exc:
                logger.error(
                    "AI_ROUTER: fallback provider=%s juga gagal (%s).",
                    fallback_id,
                    fb_exc,
                )
                raise
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
        saat method ini return, karena chunk pertama sudah "ditarik"
        untuk memastikan error provider diketahui SEBELUM stream dibuka
        ke client.
        """
        requested = self.resolve(provider_id)
        provider = self._providers[requested]
        started_at = time.monotonic()
        skip = self._should_skip(requested)

        try:
            if skip:
                raise ProviderUnavailableError(f"{requested} sedang cooldown.")
            generator = provider.chat_stream(messages, model=model)
            first_chunk: Optional[str] = next(generator, None)
        except ProviderError as exc:
            if not skip:
                self._mark_failed(requested, exc)
            logger.warning(
                "AI_ROUTER: provider=%s gagal saat streaming setelah %.2fs (%s), "
                "cek fallback.",
                requested,
                time.monotonic() - started_at,
                exc,
            )
            fallback_id = self._resolve_fallback(requested)
            if fallback_id is None:
                raise
            fallback_provider = self._providers[fallback_id]
            fb_started_at = time.monotonic()
            try:
                fb_generator = fallback_provider.chat_stream(messages)
                fb_first_chunk = next(fb_generator, None)
            except ProviderError as fb_exc:
                logger.error(
                    "AI_ROUTER: fallback provider=%s juga gagal saat streaming (%s).",
                    fallback_id,
                    fb_exc,
                )
                raise
            logger.info(
                "AI_ROUTER: fallback dipakai (stream). requested=%s used=%s "
                "first_chunk=%.2fs",
                requested,
                fallback_id,
                time.monotonic() - fb_started_at,
            )

            def _fallback_stream() -> Iterator[str]:
                if fb_first_chunk is not None:
                    yield fb_first_chunk
                yield from fb_generator

            return _fallback_stream(), ChatOutcome(fallback_id, requested, True)

        # --- jalur normal (provider utama berhasil) ---
        logger.info(
            "AI_ROUTER: provider=%s first_chunk=%.2fs",
            requested,
            time.monotonic() - started_at,
        )

        def _stream() -> Iterator[str]:
            chunks = 0
            try:
                if first_chunk is not None:
                    chunks += 1
                    yield first_chunk
                for chunk in generator:
                    chunks += 1
                    yield chunk
            finally:
                logger.info(
                    "AI_ROUTER: provider=%s stream selesai total=%.2fs chunks=%d",
                    requested,
                    time.monotonic() - started_at,
                    chunks,
                )

        return _stream(), ChatOutcome(requested, requested, False)
    
    # --------------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------------

    def _should_skip(self, provider_id: str) -> bool:
        """True jika provider sedang cooldown DAN ada fallback yang bisa dipakai."""
        return (
            time.monotonic() < self._skip_until.get(provider_id, 0.0)
            and self._resolve_fallback(provider_id) is not None
        )

    def _mark_failed(self, provider_id: str, exc: ProviderError) -> None:
        if self._cooldown_seconds > 0 and isinstance(
            exc,
            (
                ProviderTimeoutError,
                ProviderConnectionError,
                ProviderUnavailableError,
                ProviderAuthError,
            ),
        ):
            self._skip_until[provider_id] = time.monotonic() + self._cooldown_seconds

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
            return None

        return fallback_id