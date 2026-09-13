"""
test_config.py

Test untuk app/core/config.py.

Test ini TIDAK menyentuh config/config.json production — setiap test
membuat file config sementara sendiri (via tmp_path fixture pytest),
supaya aman dijalankan berkali-kali tanpa efek samping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import ConfigError, load_config


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    return config_path


def test_load_config_valid(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "assistant_name": "RIN",
            "assistant_full_name": "Responsive Intelligent Navigator",
            "language": "id",
            "ollama": {"host": "http://localhost:11434", "model": "qwen3:4b"},
        },
    )

    config = load_config(config_path)

    assert config.assistant_name == "RIN"
    assert config.assistant_full_name == "Responsive Intelligent Navigator"
    assert config.language == "id"
    assert config.ollama.host == "http://localhost:11434"
    assert config.ollama.model == "qwen3:4b"
    # timeout_seconds harus punya default yang masuk akal jika tidak diisi.
    assert config.ollama.timeout_seconds == 60


def test_load_config_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.json"

    with pytest.raises(ConfigError):
        load_config(missing_path)


def test_load_config_invalid_json(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_missing_required_field(tmp_path: Path) -> None:
    # Field "ollama" sengaja dihilangkan.
    config_path = _write_config(
        tmp_path,
        {
            "assistant_name": "RIN",
            "assistant_full_name": "Responsive Intelligent Navigator",
        },
    )

    with pytest.raises(ConfigError):
        load_config(config_path)
