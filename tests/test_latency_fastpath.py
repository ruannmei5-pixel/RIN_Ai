"""
test_latency_fastpath.py

Membuktikan optimasi latensi RIN (semua OFFLINE, tanpa API key, tanpa
menghubungi NVIDIA/Ollama/Tavily):

  1. Pertanyaan biasa TIDAK memicu request LLM apa pun untuk memutuskan
     perlu-web-search-atau-tidak (classifier hanya opt-in).
  2. Pertanyaan yang butuh info web tetap terdeteksi.
  3. Timeout NVIDIA default 25 detik dan bisa diatur lewat env.
  4. Streaming Ollama meneruskan token langsung (tidak menahan seluruh
     jawaban) saat think=False.

Jalankan:

    python -m pytest tests/test_latency_fastpath.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

import pytest

from app.core.config import (
    AIRouterConfig,
    AppConfig,
    NvidiaConfig,
    OllamaConfig,
    WebSearchConfig,
    _load_nvidia_config,
)
from app.core.search_router import needs_web_search
from app.llm.base import ChatMessage
from app.llm.ollama_client import ThinkingStreamFilter
from app.llm.router import AIProviderRouter


class ExplodingClient:
    """Classifier palsu: gagal keras jika ada yang memanggil LLM."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, model=None):  # noqa: D401
        self.calls += 1
        raise AssertionError("LLM classifier tidak boleh dipanggil di jalur cepat")


class RecordingClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def chat(self, messages, model=None):
        self.calls += 1
        return self.reply


# ------------------------------------------------------------ SEARCH ROUTER

ORDINARY = [
    "halo rin",
    "jelaskan Python untuk pemula",
    "buatkan konfigurasi mikrotik untuk vlan",
    "aku capek hari ini",
    "tolong buat kodenya sekarang",
    "bagaimana cara belajar gitar?",
    "apa rencanamu hari ini?",
    "ceritakan lelucon",
    "aku menghargai bantuanmu",
    "skoring model ini gimana?",
]


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_question_makes_no_llm_call(text):
    client = ExplodingClient()

    # Jalur default Assistant: client=None.
    assert needs_web_search(text) is False
    assert needs_web_search(text, None) is False
    assert client.calls == 0


NEEDS_WEB = [
    "siapa presiden indonesia sekarang?",
    "berapa harga terbaru RTX 5070?",
    "berapa harganya iPhone 17?",
    "apa berita teknologi terbaru hari ini?",
    "siapa yang memenangkan pertandingan tadi?",
    "bagaimana cuaca di Bandung?",
    "siapa CEO OpenAI sekarang?",
    "berapa kurs dollar hari ini?",
    "kapan rilis Python versi berikutnya?",
    "what is the latest version of node",
    "siapa juara piala dunia 2026?",
    "bagaimana kondisi ekonomi Indonesia saat ini?",
]


@pytest.mark.parametrize("text", NEEDS_WEB)
def test_web_questions_still_trigger_search(text):
    assert needs_web_search(text) is True


def test_never_keywords_still_block_weak_time_words():
    assert needs_web_search("jelaskan apa itu VLAN sekarang") is False
    assert needs_web_search("buatkan program python untuk menghitung luas lingkaran") is False


def test_empty_text_is_false():
    assert needs_web_search("") is False
    assert needs_web_search("   ") is False


def test_llm_classifier_is_opt_in_only():
    ambiguous = "ceritakan tentang perusahaan itu"

    # Tanpa client: tidak ada LLM call sama sekali.
    assert needs_web_search(ambiguous) is False

    # Dengan client eksplisit (opt-in): classifier dipakai TEPAT satu kali.
    yes = RecordingClient("YA")
    assert needs_web_search(ambiguous, yes) is True
    assert yes.calls == 1

    no = RecordingClient("TIDAK")
    assert needs_web_search(ambiguous, no) is False


def test_classifier_not_called_when_rules_decide():
    client = ExplodingClient()
    assert needs_web_search("berita terbaru hari ini", client) is True      # strong
    assert needs_web_search("jelaskan apa itu VLAN", client) is False       # never
    assert client.calls == 0


def test_llm_classifier_failure_falls_back_to_false():
    assert needs_web_search("ceritakan tentang perusahaan itu", ExplodingClient()) is False


# ------------------------------------------------ ASSISTANT: JALUR CEPAT

def _bare_assistant(llm_classifier: bool, client):
    from app.core.assistant import Assistant

    assistant = Assistant.__new__(Assistant)          # tanpa init berat (DB, dll)
    assistant.config = SimpleNamespace(
        web_search=WebSearchConfig(enabled=True, llm_classifier=llm_classifier)
    )
    assistant.client = client
    assistant._history = [ChatMessage(role="user", content="jelaskan Python untuk pemula")]
    return assistant


def test_assistant_default_does_not_call_llm_before_main_request():
    client = ExplodingClient()
    assistant = _bare_assistant(llm_classifier=False, client=client)

    messages, used, results = assistant._prepare_messages_with_optional_search(
        "ceritakan tentang perusahaan itu"
    )

    assert client.calls == 0
    assert used is False and results == []
    assert messages is assistant._history


def test_assistant_classifier_only_when_enabled():
    client = RecordingClient("TIDAK")
    assistant = _bare_assistant(llm_classifier=True, client=client)

    assistant._prepare_messages_with_optional_search("ceritakan tentang perusahaan itu")

    assert client.calls == 1


# ------------------------------------------------------------ TIMEOUT NVIDIA

def _clear_nvidia_env(monkeypatch):
    for var in (
        "NVIDIA_TIMEOUT_SECONDS",
        "NVIDIA_CONNECT_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_nvidia_timeout_defaults_are_20_to_30_seconds(monkeypatch):
    _clear_nvidia_env(monkeypatch)
    cfg = _load_nvidia_config()
    assert 20 <= cfg.timeout_seconds <= 30
    assert cfg.connect_timeout_seconds <= 10


def test_nvidia_timeout_env_override_and_clamp(monkeypatch):
    _clear_nvidia_env(monkeypatch)

    monkeypatch.setenv("NVIDIA_TIMEOUT_SECONDS", "30")
    assert _load_nvidia_config().timeout_seconds == 30

    monkeypatch.setenv("NVIDIA_TIMEOUT_SECONDS", "9999")
    assert _load_nvidia_config().timeout_seconds == 120

    monkeypatch.setenv("NVIDIA_TIMEOUT_SECONDS", "bukan-angka")
    assert _load_nvidia_config().timeout_seconds == 25


def test_router_passes_configured_timeouts_to_nvidia_provider():
    config = AppConfig(
        assistant_name="RIN",
        assistant_full_name="Responsive Intelligent Navigator",
        language="id",
        ollama=OllamaConfig("http://localhost:11434", "qwen3:4b"),
        ai=AIRouterConfig("nvidia", True, "ollama"),
        nvidia=NvidiaConfig(
            "dummy-key",
            "http://127.0.0.1:9/v1",
            "dummy-model",
            timeout_seconds=22,
            connect_timeout_seconds=3,
        ),
    )
    router = AIProviderRouter(config, ollama_client=object())
    nvidia = router.get("nvidia")

    assert nvidia.timeout_seconds == 22
    assert nvidia.connect_timeout_seconds == 3
    # Model NVIDIA tidak berubah.
    assert nvidia.active_model == "dummy-model"


def test_ollama_default_timeout_unchanged():
    assert OllamaConfig("h", "m").timeout_seconds == 60


# ------------------------------------------ STREAMING OLLAMA (think=False)

def _feed_all(flt: ThinkingStreamFilter, chunks: List[str]) -> List[str]:
    return [flt.feed(chunk) for chunk in chunks]


def test_passthrough_streams_tokens_immediately_when_think_disabled():
    flt = ThinkingStreamFilter(passthrough_if_no_think=True)

    out = _feed_all(flt, ["Ha", "lo ", "dunia"])

    # Token pertama langsung keluar, bukan menunggu stream selesai.
    assert out == ["Ha", "lo ", "dunia"]
    assert flt.finish() == ""


def test_passthrough_skips_leading_whitespace_only_chunks():
    flt = ThinkingStreamFilter(passthrough_if_no_think=True)

    assert flt.feed("\n\n") == ""
    assert flt.feed("Halo") == "Halo"


def test_passthrough_still_filters_explicit_think_block():
    flt = ThinkingStreamFilter(passthrough_if_no_think=True)

    out = _feed_all(flt, ["<thi", "nk>rahasia ", "berpikir</think>", "\n\nJawaban", " final"])

    assert "".join(out) == "\n\nJawaban final"
    assert "rahasia" not in "".join(out)


def test_legacy_mode_unchanged_buffers_until_finish():
    flt = ThinkingStreamFilter()          # perilaku lama (client tanpa think=False)

    assert _feed_all(flt, ["Ha", "lo"]) == ["", ""]
    assert flt.finish() == "Halo"


def test_legacy_mode_still_handles_untagged_reasoning():
    flt = ThinkingStreamFilter()

    out = _feed_all(flt, ["reasoning tanpa tag buka</think>", "Jawaban"])

    assert "".join(out) == "Jawaban"
