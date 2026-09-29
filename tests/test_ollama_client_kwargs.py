"""Regresi: OllamaClient hanya boleh mengirim kwarg yang valid ke ollama.Client.chat()."""

from app.llm.base import ChatMessage
from app.llm.ollama_client import OllamaClient

_ALLOWED = {"model", "messages", "tools", "think", "stream", "options", "format", "keep_alive"}


class StrictChat:
    """Meniru ollama.Client.chat(): kwarg tak dikenal -> TypeError."""

    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        unknown = set(kwargs) - _ALLOWED
        if unknown:
            raise TypeError(f"chat() got an unexpected keyword argument {sorted(unknown)[0]!r}")
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter([{"message": {"content": "Halo "}}, {"message": {"content": "dunia"}}])
        return {"message": {"content": "Halo dunia"}}


def _client():
    c = OllamaClient(host="http://localhost:11434", model="qwen3:4b", timeout_seconds=5)
    c._client = StrictChat()
    return c


MSGS = [ChatMessage(role="user", content="hai rin")]


def test_chat_stream_valid_kwargs_and_passthrough():
    c = _client()
    chunks = list(c.chat_stream(MSGS))
    assert "".join(chunks) == "Halo dunia"
    assert c._client.calls[0]["think"] is False
    assert len(chunks) >= 2  # tidak ditahan sampai stream selesai


def test_chat_valid_kwargs():
    c = _client()
    assert c.chat(MSGS) == "Halo dunia"
