import pytest

from app.core.assistant import _limit_context
from app.llm.base import ChatMessage, ProviderTimeoutError
from tests.test_provider_fallback import MSGS, make_router


def test_limit_context_keeps_system_and_last_messages():
    msgs = [ChatMessage(role="system", content="s")] + [
        ChatMessage(role="user", content=str(i)) for i in range(30)
    ]
    out = _limit_context(msgs, max_messages=12)

    assert len(out) == 13
    assert out[0].role == "system"
    assert out[-1].content == "29"
    assert len(msgs) == 31          # list asli tidak diubah


def test_cooldown_skips_nvidia_then_recovers():
    router, nvidia, _, calls = make_router()
    router._cooldown_seconds = 30

    nvidia.error = ProviderTimeoutError("timeout")
    router.chat(MSGS)
    assert calls == ["nvidia", "ollama"]          # gagal dulu, baru fallback

    calls.clear()
    _, outcome = router.chat(MSGS)
    assert calls == ["ollama"]                    # NVIDIA dilewati
    assert outcome.fallback_used and outcome.provider_requested == "nvidia"

    router._skip_until["nvidia"] = 0              # simulasi cooldown habis
    nvidia.error = None
    calls.clear()
    reply, outcome = router.chat(MSGS)
    assert calls == ["nvidia"] and outcome.fallback_used is False


def test_cooldown_does_not_skip_when_fallback_disabled():
    router, nvidia, _, calls = make_router(fallback_enabled=False)
    router._cooldown_seconds = 30

    nvidia.error = ProviderTimeoutError("timeout")
    with pytest.raises(ProviderTimeoutError):
        router.chat(MSGS)

    nvidia.error = None
    reply, _ = router.chat(MSGS)
    assert reply == "jawaban-nvidia"              # tetap dicoba, tidak diblokir