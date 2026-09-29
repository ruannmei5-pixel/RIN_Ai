"""
test_provider_fallback.py

Membuktikan perilaku AI Provider Router:

    NVIDIA = provider utama  |  Ollama = fallback per-request

TEST 1  NVIDIA tersedia            -> request memakai NVIDIA
TEST 2  NVIDIA gagal               -> request otomatis memakai Ollama
TEST 3  Setelah fallback terjadi   -> request berikutnya tetap mencoba
                                      NVIDIA terlebih dahulu

Test ini OFFLINE: tidak memakai API key, tidak menghubungi NVIDIA/Ollama
sungguhan (provider diganti fake). Jalankan:

    python -m pytest tests/test_provider_fallback.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

import pytest

from app.core.config import (
    AIRouterConfig,
    AppConfig,
    NvidiaConfig,
    OllamaConfig,
    _load_ai_router_config,
)
from app.llm.base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.llm.router import AIProviderRouter

MSGS = [ChatMessage(role="user", content="hai")]


class FakeProvider(AIProvider):
    """Provider palsu: mencatat pemanggilan, bisa dibuat gagal sesuai skenario."""

    def __init__(self, pid: str, calls: List[str]) -> None:
        self.id = pid
        self.display_name = pid
        self._calls = calls
        self.error: Optional[ProviderError] = None      # gagal sebelum chunk pertama
        self.empty_stream = False                       # stream tanpa isi

    def chat(self, messages, model=None) -> str:
        self._calls.append(self.id)
        if self.error:
            raise self.error
        return f"jawaban-{self.id}"

    def chat_stream(self, messages, model=None) -> Iterator[str]:
        self._calls.append(self.id)
        if self.error:
            raise self.error
        if self.empty_stream:
            raise ProviderResponseError(f"{self.id}: tidak menghasilkan jawaban.")
        yield f"{self.id}-a"
        yield f"{self.id}-b"


def make_router(fallback_enabled: bool = True):
    calls: List[str] = []
    config = AppConfig(
        assistant_name="RIN",
        assistant_full_name="Responsive Intelligent Navigator",
        language="id",
        ollama=OllamaConfig("http://localhost:11434", "qwen3:4b"),
        ai=AIRouterConfig("nvidia", fallback_enabled, "ollama"),
        nvidia=NvidiaConfig("dummy-key", "http://127.0.0.1:9/v1", "dummy-model"),
    )
    router = AIProviderRouter(config, ollama_client=object())
    nvidia, ollama = FakeProvider("nvidia", calls), FakeProvider("ollama", calls)
    router._providers["nvidia"] = nvidia
    router._providers["ollama"] = ollama
    return router, nvidia, ollama, calls


# ----------------------------------------------------------------- TEST 1
def test_1_nvidia_available_uses_nvidia():
    router, _, _, calls = make_router()

    reply, outcome = router.chat(MSGS)

    assert reply == "jawaban-nvidia"
    assert (outcome.provider_used, outcome.provider_requested) == ("nvidia", "nvidia")
    assert outcome.fallback_used is False
    assert calls == ["nvidia"]          # Ollama TIDAK disentuh


# ----------------------------------------------------------------- TEST 2
@pytest.mark.parametrize(
    "error",
    [
        ProviderTimeoutError("timeout"),
        ProviderConnectionError("connection error"),
        ProviderUnavailableError("unavailable / 5xx / 429"),
        ProviderAuthError("auth error"),
        ProviderNotConfiguredError("API key kosong"),
        ProviderResponseError("response error"),
    ],
)
def test_2_nvidia_fails_uses_ollama(error):
    router, nvidia, _, calls = make_router()
    nvidia.error = error

    reply, outcome = router.chat(MSGS)

    assert reply == "jawaban-ollama"
    assert outcome.provider_used == "ollama"
    assert outcome.provider_requested == "nvidia"
    assert outcome.fallback_used is True
    assert calls == ["nvidia", "ollama"]  # NVIDIA dicoba dulu, baru Ollama


# ----------------------------------------------------------------- TEST 3
def test_3_after_fallback_next_request_tries_nvidia_first():
    router, nvidia, _, calls = make_router()

    nvidia.error = ProviderConnectionError("mati")
    _, first = router.chat(MSGS)
    assert first.fallback_used is True

    # Provider utama TIDAK berubah permanen.
    assert router.config.ai.provider == "nvidia"
    assert router.default_provider_id == "nvidia"

    # Request berikutnya: NVIDIA tetap dicoba dulu (masih gagal -> fallback lagi).
    calls.clear()
    _, second = router.chat(MSGS)
    assert calls == ["nvidia", "ollama"]
    assert second.fallback_used is True

    # NVIDIA pulih -> langsung dipakai lagi, tanpa fallback.
    nvidia.error = None
    calls.clear()
    reply, third = router.chat(MSGS)
    assert reply == "jawaban-nvidia"
    assert third.provider_used == "nvidia" and third.fallback_used is False
    assert calls == ["nvidia"]


# ------------------------------------------------------------- STREAMING
def test_stream_uses_nvidia():
    router, _, _, calls = make_router()

    stream, outcome = router.chat_stream(MSGS)

    assert "".join(stream) == "nvidia-anvidia-b"
    assert outcome.provider_used == "nvidia" and outcome.fallback_used is False
    assert calls == ["nvidia"]


def test_stream_nvidia_fails_falls_back_to_ollama_then_recovers():
    router, nvidia, _, calls = make_router()

    nvidia.error = ProviderTimeoutError("timeout")
    stream, outcome = router.chat_stream(MSGS)
    assert "".join(stream) == "ollama-aollama-b"
    assert outcome.provider_used == "ollama"
    assert outcome.provider_requested == "nvidia"
    assert outcome.fallback_used is True

    nvidia.error = None
    calls.clear()
    stream, outcome = router.chat_stream(MSGS)
    assert "".join(stream) == "nvidia-anvidia-b"
    assert outcome.fallback_used is False
    assert calls == ["nvidia"]


def test_stream_nvidia_empty_stream_falls_back():
    router, nvidia, _, _ = make_router()
    nvidia.empty_stream = True

    stream, outcome = router.chat_stream(MSGS)

    assert "".join(stream) == "ollama-aollama-b"
    assert outcome.fallback_used is True


# ------------------------------------------------------- FALLBACK OFF / BOTH FAIL
def test_fallback_disabled_raises_nvidia_error():
    router, nvidia, _, calls = make_router(fallback_enabled=False)
    nvidia.error = ProviderAuthError("auth error")

    with pytest.raises(ProviderAuthError):
        router.chat(MSGS)
    assert calls == ["nvidia"]


def test_both_fail_raises_error():
    router, nvidia, ollama, _ = make_router()
    nvidia.error = ProviderConnectionError("nvidia mati")
    ollama.error = ProviderConnectionError("ollama mati")

    with pytest.raises(ProviderConnectionError):
        router.chat(MSGS)


# ------------------------------------------------------------ PROVIDER LIST
def test_only_nvidia_and_ollama_are_registered():
    router, *_ = make_router()
    assert sorted(router.all_providers()) == ["nvidia", "ollama"]


def test_stale_or_unknown_provider_id_resolves_to_primary_not_ollama():
    router, *_ = make_router()
    assert router.resolve("provider-lama-yang-dihapus") == "nvidia"
    assert router.resolve("") == "nvidia"
    assert router.resolve(None) == "nvidia"
    assert router.resolve("ollama") == "ollama"     # override eksplisit tetap boleh


def test_env_defaults_and_invalid_values(monkeypatch):
    for var in ("AI_PROVIDER", "AI_FALLBACK_PROVIDER", "AI_FALLBACK_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    cfg = _load_ai_router_config()
    assert (cfg.provider, cfg.fallback_provider, cfg.fallback_enabled) == ("nvidia", "ollama", True)

    monkeypatch.setenv("AI_PROVIDER", "nilai-tidak-dikenal")
    assert _load_ai_router_config().provider == "nvidia"


def test_no_openrouter_reference_left_in_backend():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if "openrouter" in p.read_text(encoding="utf-8").lower()
    ]
    assert offenders == []
    assert not (app_dir / "llm" / "providers" / "openrouter_provider.py").exists()
