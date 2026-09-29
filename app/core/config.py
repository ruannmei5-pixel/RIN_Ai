"""
config.py

Modul untuk memuat konfigurasi RIN dari file `config/config.json`.

Tujuan modul ini:
- Tidak ada nilai penting yang di-hardcode di dalam kode.
- Konfigurasi (nama assistant, host Ollama, model, dll) mudah diubah
  cukup dengan mengedit file JSON, tanpa menyentuh source code.

Catatan Phase 1:
Baru field-field dasar yang digunakan (assistant_name, ollama.host, ollama.model).
Field tambahan akan digunakan pada phase-phase berikutnya.

AUTOMATIC WEB SEARCH:
- Menambahkan section "web_search" (enabled, max_results, timeout_seconds)
  di config.json. Ini HANYA berisi pengaturan non-rahasia.
- API key web search (TAVILY_API_KEY) SENGAJA TIDAK ada di config.json:
  key selalu dibaca dari environment variable / file .env lewat
  python-dotenv (load_dotenv() di bawah), TIDAK PERNAH di-hardcode dan
  TIDAK PERNAH disimpan di file yang di-commit ke Git (lihat .gitignore).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from app.core.logger import get_logger

logger = get_logger()


# Path root project dihitung relatif terhadap file ini,
# supaya tidak bergantung pada direktori tempat script dijalankan
# dan tidak hardcode path Windows.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "config.json"

# Muat variabel dari file .env di root project (jika ada) ke
# environment process ini, SEBELUM AppConfig/web_search service
# membaca os.getenv(...). Aman dipanggil berkali-kali (idempotent) dan
# TIDAK menimpa environment variable yang sudah diset di luar (mis. di
# shell/Docker), karena default override=False.
load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(Exception):
    """Dilempar ketika file konfigurasi tidak ditemukan atau tidak valid."""


@dataclass
class OllamaConfig:
    host: str
    model: str
    timeout_seconds: int = 60


@dataclass
class WebSearchConfig:
    """
    Pengaturan AUTOMATIC WEB SEARCH.

    Semua field di sini non-rahasia (aman ada di config.json).
    API key TIDAK ada di sini — lihat catatan module-level di atas.
    """

    enabled: bool = True
    max_results: int = 3
    timeout_seconds: int = 8


@dataclass
class NvidiaConfig:
    """
    TAHAP 3 — Konfigurasi NVIDIA AI provider.

    SEMUANYA dibaca dari environment variable (NVIDIA_API_KEY,
    NVIDIA_BASE_URL, NVIDIA_MODEL), TIDAK PERNAH di-hardcode dan TIDAK
    PERNAH ada di config.json (config.json tidak menyimpan secret).
    """

    api_key: str = ""
    base_url: str = ""
    model: str = ""


@dataclass
class OpenRouterConfig:
    """
    TAHAP 3 — Konfigurasi OpenRouter provider.

    Sama seperti NvidiaConfig: seluruhnya dari environment variable
    (OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL).
    """

    api_key: str = ""
    base_url: str = ""
    model: str = ""


@dataclass
class AIRouterConfig:
    """
    TAHAP 3 — Konfigurasi terpusat AI Provider Router.

    provider           : "ollama" | "nvidia" | "openrouter"
                          (env AI_PROVIDER, default "ollama")
    fallback_enabled    : env AI_FALLBACK_ENABLED (default True)
    fallback_provider   : env AI_FALLBACK_PROVIDER (default "ollama")

    Provider selection SENGAJA hanya ada di SATU tempat (di sini +
    app/llm/router.py), bukan tersebar di banyak file.
    """

    provider: str = "ollama"
    fallback_enabled: bool = True
    fallback_provider: str = "ollama"


@dataclass
class AppConfig:
    assistant_name: str
    assistant_full_name: str
    language: str
    ollama: OllamaConfig
    # PHASE 6J: override enable/disable per tool, mis. {"file_reader": false}.
    # Opsional — jika field "tools" tidak ada di config.json, semua tool
    # bawaan tetap aktif (default masing-masing Tool.enabled = True).
    tools_enabled: Dict[str, bool] = field(default_factory=dict)
    # AUTOMATIC WEB SEARCH: opsional — jika field "web_search" tidak ada
    # di config.json (mis. config.json lama sebelum fitur ini), dipakai
    # default WebSearchConfig() di atas (enabled=True, 3 hasil, 8 detik).
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    # TAHAP 3 — MULTI AI PROVIDER: provider selection (env-based) +
    # konfigurasi cloud provider (env-based, tidak ada di config.json).
    ai: AIRouterConfig = field(default_factory=AIRouterConfig)
    nvidia: NvidiaConfig = field(default_factory=NvidiaConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)


def load_config(config_path: Path = CONFIG_PATH) -> AppConfig:
    """
    Memuat konfigurasi dari file JSON dan mengembalikan objek AppConfig.

    Args:
        config_path: Path menuju file config.json.

    Raises:
        ConfigError: jika file tidak ditemukan atau format JSON tidak valid,
            atau ada field wajib yang hilang.
    """
    if not config_path.exists():
        raise ConfigError(
            f"File konfigurasi tidak ditemukan: {config_path}\n"
            "Pastikan file 'config/config.json' ada di root project."
        )

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data: Dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"File konfigurasi '{config_path}' berisi JSON yang tidak valid: {exc}"
        ) from exc

    try:
        ollama_raw = data["ollama"]
        ollama_config = OllamaConfig(
            host=ollama_raw["host"],
            model=ollama_raw["model"],
            timeout_seconds=int(ollama_raw.get("timeout_seconds", 60)),
        )

        raw_tools = data.get("tools", {})
        tools_enabled: Dict[str, bool] = {}
        if isinstance(raw_tools, dict):
            for tool_name, tool_enabled in raw_tools.items():
                tools_enabled[str(tool_name)] = bool(tool_enabled)

        raw_web_search = data.get("web_search", {})
        if not isinstance(raw_web_search, dict):
            raw_web_search = {}

        web_search_config = WebSearchConfig(
            enabled=bool(raw_web_search.get("enabled", True)),
            max_results=int(raw_web_search.get("max_results", 3)),
            timeout_seconds=int(raw_web_search.get("timeout_seconds", 8)),
        )

        ai_config = _load_ai_router_config()
        nvidia_config = _load_nvidia_config()
        openrouter_config = _load_openrouter_config()

        app_config = AppConfig(
            assistant_name=data["assistant_name"],
            assistant_full_name=data["assistant_full_name"],
            language=data.get("language", "id"),
            ollama=ollama_config,
            tools_enabled=tools_enabled,
            web_search=web_search_config,
            ai=ai_config,
            nvidia=nvidia_config,
            openrouter=openrouter_config,
        )
    except KeyError as exc:
        raise ConfigError(
            f"Field konfigurasi wajib hilang pada '{config_path}': {exc}"
        ) from exc

    return app_config


# ============================================================
# TAHAP 3 — MULTI AI PROVIDER: environment-based config
# ============================================================
#
# Provider selection & kredensial cloud provider SENGAJA dibaca dari
# environment variable (bukan config.json), sesuai instruksi TAHAP 3:
# "Buat konfigurasi terpusat" + "API key HANYA berada di
# backend/environment". Fungsi-fungsi ini dipanggil oleh load_config()
# di atas, SETELAH load_dotenv(PROJECT_ROOT / ".env") pada module-level
# sudah berjalan, sehingga .env ikut terbaca.

_VALID_PROVIDER_IDS = ("ollama", "nvidia", "openrouter")


def _load_ai_router_config() -> "AIRouterConfig":
    provider = os.getenv("AI_PROVIDER", "ollama").strip().lower() or "ollama"
    if provider not in _VALID_PROVIDER_IDS:
        logger.warning(
            "AI_PROVIDER=%r tidak dikenal (harus salah satu dari %s). "
            "Memakai 'ollama'.",
            provider,
            _VALID_PROVIDER_IDS,
        )
        provider = "ollama"

    fallback_provider = os.getenv("AI_FALLBACK_PROVIDER", "ollama").strip().lower() or "ollama"
    if fallback_provider not in _VALID_PROVIDER_IDS:
        logger.warning(
            "AI_FALLBACK_PROVIDER=%r tidak dikenal. Memakai 'ollama'.",
            fallback_provider,
        )
        fallback_provider = "ollama"

    fallback_enabled_raw = os.getenv("AI_FALLBACK_ENABLED", "true").strip().lower()
    fallback_enabled = fallback_enabled_raw not in ("false", "0", "no", "off")

    return AIRouterConfig(
        provider=provider,
        fallback_enabled=fallback_enabled,
        fallback_provider=fallback_provider,
    )


def _load_nvidia_config() -> "NvidiaConfig":
    return NvidiaConfig(
        api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
        base_url=os.getenv("NVIDIA_BASE_URL", "").strip().rstrip("/"),
        model=os.getenv("NVIDIA_MODEL", "").strip(),
    )


def _load_openrouter_config() -> "OpenRouterConfig":
    return OpenRouterConfig(
        api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        base_url=(
            os.getenv("OPENROUTER_BASE_URL", "").strip().rstrip("/")
            or "https://openrouter.ai/api/v1"
        ),
        model=os.getenv("OPENROUTER_MODEL", "").strip(),
    )
