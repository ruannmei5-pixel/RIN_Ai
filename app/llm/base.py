"""
base.py

TAHAP 3 — MULTI AI PROVIDER.

Abstraction layer seragam untuk semua AI inference provider yang
didukung RIN (Ollama, NVIDIA AI, ).

Kenapa modul ini dibuat:
- Sebelum TAHAP 3, seluruh RIN (assistant.py, search_router.py, dsb)
  bicara LANGSUNG ke `OllamaClient` (app/llm/ollama_client.py).
- Supaya bisa menambah NVIDIA AI TANPA mengubah struktur
  response di seluruh aplikasi, semua provider (termasuk Ollama)
  sekarang diakses lewat interface `AIProvider` yang sama:

      chat(messages)        -> str
      chat_stream(messages) -> Iterator[str]
      health_check()        -> ProviderHealth
      get_models()          -> List[str]
      is_configured()       -> bool

- Response SUDAH dinormalisasi di layer provider masing-masing
  (lihat app/llm/providers/*.py): caller (Assistant, routes.py) tidak
  pernah perlu tahu apakah balasan datang dari Ollama, NVIDIA.

- Error dari ketiga provider juga dinormalisasi ke satu hierarchy
  `ProviderError` di bawah, supaya app/api/routes.py bisa memetakan
  status HTTP dengan cara yang sama untuk provider mana pun (lihat
  `_map_provider_error` di app/api/routes.py).

`ChatMessage` DIPAKAI ULANG dari app/llm/ollama_client.py (bukan
didefinisikan ulang di sini) supaya tidak ada dua tipe "message" yang
berbeda beredar di codebase yang sama.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, List, Optional

from app.llm.ollama_client import ChatMessage

__all__ = [
    "ChatMessage",
    "ProviderHealth",
    "AIProvider",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderConnectionError",
    "ProviderTimeoutError",
    "ProviderAuthError",
    "ProviderModelNotFoundError",
    "ProviderResponseError",
    "ProviderUnavailableError",
]


# ============================================================
# ERROR HIERARCHY (dinormalisasi lintas provider)
# ============================================================

class ProviderError(Exception):
    """Error umum yang berkaitan dengan AI provider mana pun."""


class ProviderNotConfiguredError(ProviderError):
    """Provider belum dikonfigurasi (mis. API key kosong)."""


class ProviderConnectionError(ProviderError):
    """Provider tidak dapat dihubungi (jaringan/DNS/refused)."""


class ProviderTimeoutError(ProviderError):
    """Request ke provider melebihi batas waktu."""


class ProviderAuthError(ProviderError):
    """API key ditolak provider (401/403)."""


class ProviderModelNotFoundError(ProviderError):
    """Model yang diminta tidak ditemukan/tidak tersedia di provider."""


class ProviderResponseError(ProviderError):
    """Response provider tidak dapat dibaca / status error lain."""


class ProviderUnavailableError(ProviderError):
    """Provider sedang tidak tersedia (5xx/overloaded)."""


# ============================================================
# HEALTH
# ============================================================

@dataclass
class ProviderHealth:
    """
    Status kesehatan satu provider, HANYA berdasarkan pengecekan nyata
    (bukan diasumsikan "connected" hanya karena dipilih user — lihat
    BATASAN pada TAHAP 3).
    """

    configured: bool
    available: bool
    detail: str = ""


# ============================================================
# INTERFACE
# ============================================================

class AIProvider(ABC):
    """
    Interface seragam untuk satu AI inference provider.

    Implementasi konkret: OllamaProvider, NvidiaProvider
    (lihat app/llm/providers/).
    """

    #: id pendek, dipakai di config/env (AI_PROVIDER) dan endpoint API.
    id: str = ""

    #: nama untuk ditampilkan di UI (chat header, settings).
    display_name: str = ""

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
    ) -> str:
        """Mengirim `messages` dan mengembalikan balasan final (str)."""
        raise NotImplementedError

    @abstractmethod
    def chat_stream(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
    ) -> Iterator[str]:
        """Sama seperti chat(), tapi mengembalikan balasan secara streaming."""
        raise NotImplementedError

    def get_models(self) -> List[str]:
        """
        Mengembalikan daftar model yang tersedia dari provider ini,
        jika provider mendukung dynamic model discovery.

        Default: list kosong (caller akan fallback ke model dari
        environment/configuration — lihat routes.py:list_models).
        """
        return []

    def health_check(self) -> ProviderHealth:
        """
        Default health check: hanya melaporkan `is_configured()`.
        Provider yang bisa dites nyata (Ollama, NVIDIA )
        override method ini.
        """
        configured = self.is_configured()
        return ProviderHealth(
            configured=configured,
            available=configured,
            detail="Belum dikonfigurasi." if not configured else "",
        )

    def is_configured(self) -> bool:
        """True jika provider ini punya konfigurasi minimal untuk dipakai."""
        return True

    @property
    def active_model(self) -> str:
        """Model default provider ini (dari environment/configuration)."""
        return ""
