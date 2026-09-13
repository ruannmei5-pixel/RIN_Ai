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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


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

        app_config = AppConfig(
            assistant_name=data["assistant_name"],
            assistant_full_name=data["assistant_full_name"],
            language=data.get("language", "id"),
            ollama=ollama_config,
            tools_enabled=tools_enabled,
            web_search=web_search_config,
        )
    except KeyError as exc:
        raise ConfigError(
            f"Field konfigurasi wajib hilang pada '{config_path}': {exc}"
        ) from exc

    return app_config
