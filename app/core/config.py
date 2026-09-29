"""
config.py

Modul untuk memuat konfigurasi RIN dari file `config/config.json`
dan environment variable (.env).

Tujuan modul ini:
- Tidak ada nilai penting yang di-hardcode di dalam kode.
- Konfigurasi non-rahasia (nama assistant, host Ollama, model, web search)
  ada di config/config.json.
- Semua secret (NVIDIA_API_KEY, TAVILY_API_KEY) HANYA dibaca dari
  environment variable / file .env lewat python-dotenv, TIDAK PERNAH
  di-hardcode dan TIDAK PERNAH disimpan di file yang di-commit ke Git.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from app.core.logger import get_logger

logger = get_logger()


# Path root project dihitung relatif terhadap file ini,
# supaya tidak bergantung pada direktori tempat script dijalankan.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "config.json"

# Muat variabel dari file .env di root project (jika ada) ke environment.
# Tidak menimpa environment variable yang sudah diset di luar
# (override=False secara default).
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
    API key (TAVILY_API_KEY) TIDAK ada di sini.
    """

    enabled: bool = True
    max_results: int = 3
    timeout_seconds: int = 8
    # Classifier LLM untuk kasus ambigu DEFAULT MATI (lihat search_router.py).
    # Override lewat env SEARCH_ROUTER_LLM_CLASSIFIER.
    llm_classifier: bool = False


@dataclass
class NvidiaConfig:
    """
    Konfigurasi NVIDIA AI provider (provider utama).

    SEMUANYA dari environment variable, TIDAK PERNAH ada di config.json.
    timeout_seconds         = batas tunggu token pertama / jeda antar chunk
    connect_timeout_seconds = batas membuka koneksi
    """

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = 25.0
    connect_timeout_seconds: float = 5.0


@dataclass
class AIRouterConfig:
    """
    Konfigurasi terpusat AI Provider Router.

    provider           : "nvidia" | "ollama"
                          (env AI_PROVIDER, default "nvidia" = PROVIDER UTAMA)
    fallback_enabled    : env AI_FALLBACK_ENABLED (default True)
    fallback_provider   : env AI_FALLBACK_PROVIDER (default "ollama")

    Nilai ini STATIS (dibaca sekali dari environment). Fallback terjadi
    PER REQUEST di app/llm/router.py dan TIDAK PERNAH mengubah `provider`.
    """

    provider: str = "nvidia"
    fallback_enabled: bool = True
    fallback_provider: str = "ollama"


@dataclass
class AppConfig:
    assistant_name: str
    assistant_full_name: str
    language: str
    ollama: OllamaConfig
    # Override enable/disable per tool, mis. {"file_reader": false}.
    tools_enabled: Dict[str, bool] = field(default_factory=dict)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    ai: AIRouterConfig = field(default_factory=AIRouterConfig)
    nvidia: NvidiaConfig = field(default_factory=NvidiaConfig)


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

_VALID_PROVIDER_IDS = ("nvidia", "ollama")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """Baca float dari env; nilai kosong/tidak valid -> default, lalu di-clamp."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r bukan angka, memakai default %s.", name, raw, default)
        return default
    return max(minimum, min(maximum, value))


def _load_ai_router_config() -> AIRouterConfig:
    provider = os.getenv("AI_PROVIDER", "nvidia").strip().lower() or "nvidia"
    if provider not in _VALID_PROVIDER_IDS:
        logger.warning(
            "AI_PROVIDER=%r tidak dikenal (harus salah satu dari %s). "
            "Memakai 'nvidia'.",
            provider,
            _VALID_PROVIDER_IDS,
        )
        provider = "nvidia"

    fallback_provider = (
        os.getenv("AI_FALLBACK_PROVIDER", "ollama").strip().lower() or "ollama"
    )
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


def _load_nvidia_config() -> NvidiaConfig:
    return NvidiaConfig(
        api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
        base_url=os.getenv("NVIDIA_BASE_URL", "").strip().rstrip("/"),
        model=os.getenv("NVIDIA_MODEL", "").strip(),
        timeout_seconds=_env_float("NVIDIA_TIMEOUT_SECONDS", 25.0, 5.0, 120.0),
        connect_timeout_seconds=_env_float(
            "NVIDIA_CONNECT_TIMEOUT_SECONDS", 5.0, 1.0, 30.0
        ),
    )


# ============================================================
# LOAD
# ============================================================

def load_config(config_path: Path = CONFIG_PATH) -> AppConfig:
    """
    Memuat konfigurasi dari file JSON + environment dan mengembalikan AppConfig.

    Raises:
        ConfigError: jika file tidak ditemukan, JSON tidak valid,
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
        # OLLAMA_BASE_URL / OLLAMA_MODEL (opsional) menimpa config.json
        # jika diisi; jika kosong, config.json tetap dipakai apa adanya.
        ollama_config = OllamaConfig(
            host=(
                os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
                or ollama_raw["host"]
            ),
            model=(os.getenv("OLLAMA_MODEL", "").strip() or ollama_raw["model"]),
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
            llm_classifier=_env_bool(
                "SEARCH_ROUTER_LLM_CLASSIFIER",
                bool(raw_web_search.get("llm_classifier", False)),
            ),
        )

        app_config = AppConfig(
            assistant_name=data["assistant_name"],
            assistant_full_name=data["assistant_full_name"],
            language=data.get("language", "id"),
            ollama=ollama_config,
            tools_enabled=tools_enabled,
            web_search=web_search_config,
            ai=_load_ai_router_config(),
            nvidia=_load_nvidia_config(),
        )
    except KeyError as exc:
        raise ConfigError(
            f"Field konfigurasi wajib hilang pada '{config_path}': {exc}"
        ) from exc

    return app_config
