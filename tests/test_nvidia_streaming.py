"""
test_nvidia_streaming.py

Menguji lapisan HTTP NVIDIA (app/llm/providers/openai_compatible.py)
secara OFFLINE memakai httpx.MockTransport (tidak ada koneksi jaringan,
tidak butuh API key):

  - token pertama diteruskan segera (streaming, bukan menunggu semua)
  - timeout token pertama -> ProviderTimeoutError -> fallback Ollama
  - fallback hanya untuk request itu (NVIDIA tetap provider utama)
  - httpx.Client dipakai ulang (keep-alive) antar request
  - model NVIDIA yang dikirim tidak berubah

Jalankan:

    python -m pytest tests/test_nvidia_streaming.py -v
"""

from __future__ import annotations

import json
import time
from typing import Iterator, List

import pytest

httpx = pytest.importorskip("httpx")

from app.core.config import (  # noqa: E402
    AIRouterConfig,
    AppConfig,
    NvidiaConfig,
    OllamaConfig,
)
from app.llm.base import (  # noqa: E402
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderTimeoutError,
)
from app.llm.providers.nvidia_provider import NvidiaProvider  # noqa: E402
from app.llm.router import AIProviderRouter  # noqa: E402

MSGS = [ChatMessage(role="user", content="hai")]
MODEL = "nvidia/model-tes"


def _sse(*pieces: str) -> bytes:
    lines = []
    for piece in pieces:
        event = {"choices": [{"delta": {"content": piece}}]}
        lines.append(f"data: {json.dumps(event)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _provider(handler, timeout: float = 25.0) -> NvidiaProvider:
    return NvidiaProvider(
        api_key="dummy-key",
        base_url="https://nvidia.test/v1",
        model=MODEL,
        timeout_seconds=timeout,
        transport=httpx.MockTransport(handler),
    )


class _KeepAliveOnlyStream(httpx.SyncByteStream):
    """Server yang terus mengirim keep-alive tapi tidak pernah mengirim token."""

    def __iter__(self) -> Iterator[bytes]:
        for _ in range(200):
            time.sleep(0.05)
            yield b": keep-alive\n"


class _FakeOllama(AIProvider):
    id = "ollama"
    display_name = "ollama"

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, model=None) -> str:
        self.calls += 1
        return "jawaban-ollama"

    def chat_stream(self, messages, model=None) -> Iterator[str]:
        self.calls += 1
        yield "ollama-a"
        yield "ollama-b"


def _router(nvidia: NvidiaProvider):
    config = AppConfig(
        assistant_name="RIN",
        assistant_full_name="Responsive Intelligent Navigator",
        language="id",
        ollama=OllamaConfig("http://localhost:11434", "qwen3:4b"),
        ai=AIRouterConfig("nvidia", True, "ollama"),
        nvidia=NvidiaConfig("dummy-key", "https://nvidia.test/v1", MODEL),
    )
    router = AIProviderRouter(config, ollama_client=object())
    ollama = _FakeOllama()
    router._providers["nvidia"] = nvidia
    router._providers["ollama"] = ollama
    return router, ollama


# ---------------------------------------------------------------- STREAMING

def test_stream_yields_chunks_in_order_and_sends_configured_model():
    seen: List[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_sse("Ha", "lo", " dunia"))

    provider = _provider(handler)
    chunks = list(provider.chat_stream(MSGS))

    assert chunks == ["Ha", "lo", " dunia"]
    assert seen[0]["model"] == MODEL          # model NVIDIA tidak diganti
    assert seen[0]["stream"] is True


def test_first_chunk_is_available_before_stream_is_consumed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse("pertama", "kedua"))

    generator = _provider(handler).chat_stream(MSGS)

    assert next(generator) == "pertama"       # tanpa menunggu chunk berikutnya


# --------------------------------------------------------- CLIENT PERSISTEN

def test_http_client_is_reused_across_requests():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=_sse("ok"))

    provider = _provider(handler)
    list(provider.chat_stream(MSGS))
    first_client = provider._client
    list(provider.chat_stream(MSGS))

    assert first_client is not None
    assert provider._client is first_client   # koneksi/keep-alive dipakai ulang
    assert calls["n"] == 2

    provider.close()
    assert provider._client is None


# ------------------------------------------------------------------ ERROR

def test_auth_error_is_mapped():
    provider = _provider(lambda request: httpx.Response(401, text="nope"))

    with pytest.raises(ProviderAuthError):
        list(provider.chat_stream(MSGS))


def test_first_token_deadline_raises_timeout_even_with_keepalives():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_KeepAliveOnlyStream())

    provider = _provider(handler, timeout=0.2)
    started = time.monotonic()

    with pytest.raises(ProviderTimeoutError):
        list(provider.chat_stream(MSGS))

    assert time.monotonic() - started < 2.0   # tidak menggantung


# ----------------------------------------------------------------- FALLBACK

def test_timeout_falls_back_to_ollama_for_that_request_only():
    state = {"nvidia_down": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["nvidia_down"]:
            raise httpx.ConnectTimeout("timeout", request=request)
        return httpx.Response(200, content=_sse("nvidia-a", "nvidia-b"))

    router, ollama = _router(_provider(handler))

    stream, outcome = router.chat_stream(MSGS)
    assert "".join(stream) == "ollama-aollama-b"
    assert outcome.provider_used == "ollama"
    assert outcome.provider_requested == "nvidia"
    assert outcome.fallback_used is True

    # Provider utama TIDAK berubah; request berikutnya mencoba NVIDIA lagi.
    assert router.config.ai.provider == "nvidia"
    state["nvidia_down"] = False
    stream, outcome = router.chat_stream(MSGS)
    assert "".join(stream) == "nvidia-anvidia-b"
    assert outcome.provider_used == "nvidia" and outcome.fallback_used is False
    assert ollama.calls == 1                  # Ollama hanya dipakai sekali


def test_normal_request_never_touches_ollama():
    router, ollama = _router(
        _provider(lambda request: httpx.Response(200, content=_sse("a", "b")))
    )

    stream, outcome = router.chat_stream(MSGS)

    assert "".join(stream) == "ab"
    assert outcome.fallback_used is False
    assert ollama.calls == 0
