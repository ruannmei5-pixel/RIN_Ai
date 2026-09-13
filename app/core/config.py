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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


# Path root project dihitung relatif terhadap file ini,
# supaya tidak bergantung pada direktori tempat script dijalankan
# dan tidak hardcode path Windows.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "config.json"


class ConfigError(Exception):
    """Dilempar ketika file konfigurasi tidak ditemukan atau tidak valid."""


@dataclass
class OllamaConfig:
    host: str
    model: str
    timeout_seconds: int = 60


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

        app_config = AppConfig(
            assistant_name=data["assistant_name"],
            assistant_full_name=data["assistant_full_name"],
            language=data.get("language", "id"),
            ollama=ollama_config,
            tools_enabled=tools_enabled,
        )
    except KeyError as exc:
        raise ConfigError(
            f"Field konfigurasi wajib hilang pada '{config_path}': {exc}"
        ) from exc

    return app_config
