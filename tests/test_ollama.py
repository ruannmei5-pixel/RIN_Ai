"""
test_ollama.py

Test untuk konektivitas Ollama, ketersediaan model, dan respons dasar
Assistant.

PENTING: Test-test ini membutuhkan Ollama yang benar-benar berjalan di
laptop (bukan mock), karena tujuannya memverifikasi integrasi nyata
"RIN -> Python -> Ollama -> qwen3:4b". Jika Ollama tidak berjalan atau
model belum di-pull, test akan di-skip (bukan gagal/error), supaya
test suite tetap bisa dijalankan di lingkungan tanpa Ollama (mis. CI).

Test ini tidak menyentuh database production karena Phase 1 belum
memiliki database (memory SQLite baru ditambahkan pada PHASE 4).
"""

from __future__ import annotations

import pytest
from ollama import Client

from app.core.assistant import Assistant
from app.core.config import load_config
from app.llm.ollama_client import OllamaConnectionError, OllamaModelNotFoundError


@pytest.fixture(scope="module")
def config():
    return load_config()


def _skip_if_ollama_unreachable(host: str) -> None:
    try:
        Client(host=host).list()
    except Exception as exc:  # noqa: BLE001 - kegagalan apa pun berarti skip, bukan gagal
        pytest.skip(f"Ollama tidak dapat dijangkau di {host}: {exc}")


def test_ollama_connectivity(config) -> None:
    """Memastikan Ollama API dapat dijangkau di host yang dikonfigurasi."""
    _skip_if_ollama_unreachable(config.ollama.host)


def test_model_availability(config) -> None:
    """Memastikan model yang dikonfigurasi (mis. qwen3:4b) sudah di-pull di Ollama."""
    _skip_if_ollama_unreachable(config.ollama.host)

    client = Client(host=config.ollama.host)
    models_response = client.list()
    available_models = {m["model"] for m in models_response.get("models", [])}

    if not available_models:
        pytest.skip("Tidak ada model yang terdaftar di Ollama untuk diperiksa.")

    assert config.ollama.model in available_models, (
        f"Model '{config.ollama.model}' belum di-pull. "
        f"Jalankan: ollama pull {config.ollama.model}"
    )


def test_basic_assistant_response(config) -> None:
    """Memastikan Assistant dapat mengirim pesan sederhana dan menerima balasan teks."""
    _skip_if_ollama_unreachable(config.ollama.host)

    assistant = Assistant(config)

    try:
        reply = assistant.ask("Halo")
    except OllamaModelNotFoundError:
        pytest.skip(f"Model '{config.ollama.model}' belum di-pull di Ollama.")
    except OllamaConnectionError:
        pytest.skip("Ollama tidak dapat dijangkau saat mengirim pesan.")

    assert isinstance(reply, str)
    assert len(reply.strip()) > 0
