"""
openai_compatible.py

TAHAP 3 — Base class untuk provider cloud yang kompatibel dengan
OpenAI-style Chat Completions API (`POST {base_url}/chat/completions`).

Dipakai oleh:
- NvidiaProvider  (app/llm/providers/nvidia_provider.py)
- OpenRouterProvider (app/llm/providers/openrouter_provider.py)

Kedua provider di atas HANYA berbeda pada:
- nama/id
- base_url default
- (opsional) header tambahan

Semua logic HTTP, streaming (SSE), dan error handling ada di SATU
tempat ini supaya tidak ada dua implementasi yang berbeda untuk
"provider OpenAI-compatible" di seluruh aplikasi (lihat instruksi
TAHAP 3: "Jangan membuat masing-masing provider memiliki struktur
response yang berbeda").

KEAMANAN:
- API key HANYA dipakai untuk membangun header Authorization di sini,
  di backend. Tidak pernah dikembalikan/di-log.
- Pesan error SENGAJA disaring supaya tidak pernah menyertakan API key
  atau isi header Authorization (lihat `_sanitize_error_text`).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

import httpx

from app.core.logger import get_logger
from app.llm.base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderHealth,
    ProviderModelNotFoundError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = get_logger()


def _sanitize_error_text(text: str, api_key: str) -> str:
    """Pastikan API key tidak pernah muncul di pesan error, walau tertukar."""
    if api_key:
        text = text.replace(api_key, "***")
    return text[:300]


class OpenAICompatibleProvider(AIProvider):
    """
    Provider generik untuk API bergaya OpenAI Chat Completions.

    Subclass HANYA perlu mengisi `id`, `display_name`, dan default
    base_url lewat constructor masing-masing (lihat nvidia_provider.py
    / openrouter_provider.py).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").rstrip("/")
        self.model = (model or "").strip()
        self.timeout_seconds = timeout_seconds
        self._extra_headers = extra_headers or {}

    # --------------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.base_url)

    @property
    def active_model(self) -> str:
        return self.model

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self._extra_headers)
        return headers

    def _require_configured(self) -> None:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                f"{self.display_name}: API key belum dikonfigurasi."
            )
        if not self.model:
            raise ProviderNotConfiguredError(
                f"{self.display_name}: model belum dikonfigurasi "
                f"(set environment variable model-nya)."
            )

    @staticmethod
    def _messages_payload(messages: List[ChatMessage]) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    # --------------------------------------------------------------
    # CHAT (non-streaming)
    # --------------------------------------------------------------

    def chat(self, messages: List[ChatMessage], model: Optional[str] = None) -> str:
        self._require_configured()
        active_model = (model or self.model).strip()

        payload = {
            "model": active_model,
            "messages": self._messages_payload(messages),
            "stream": False,
        }

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self.display_name}: request melebihi {self.timeout_seconds} detik."
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"{self.display_name}: tidak dapat terhubung ({exc.__class__.__name__})."
            ) from exc

        self._raise_for_status(response)

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                f"{self.display_name}: response tidak dapat dibaca."
            ) from exc

        if not content or not str(content).strip():
            raise ProviderResponseError(
                f"{self.display_name}: mengembalikan balasan kosong."
            )

        return str(content)

    # --------------------------------------------------------------
    # CHAT (streaming, SSE)
    # --------------------------------------------------------------

    def chat_stream(self, messages: List[ChatMessage], model: Optional[str] = None) -> Iterator[str]:
        self._require_configured()
        active_model = (model or self.model).strip()

        payload = {
            "model": active_model,
            "messages": self._messages_payload(messages),
            "stream": True,
        }

        full_reply = ""

        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as response:
                if response.status_code >= 400:
                    # Baca body error (bukan stream) sebelum melempar.
                    response.read()
                    self._raise_for_status(response)

                for line in response.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()

                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)
                    except ValueError:
                        continue

                    try:
                        delta = event["choices"][0].get("delta", {})
                        chunk = delta.get("content") or ""
                    except (KeyError, IndexError, TypeError):
                        chunk = ""

                    if chunk:
                        full_reply += chunk
                        yield chunk

        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self.display_name}: streaming timeout setelah {self.timeout_seconds} detik."
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"{self.display_name}: koneksi streaming terputus ({exc.__class__.__name__})."
            ) from exc

        if not full_reply.strip():
            raise ProviderResponseError(
                f"{self.display_name}: tidak menghasilkan jawaban."
            )

    # --------------------------------------------------------------
    # ERROR MAPPING
    # --------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        status = response.status_code
        body_text = _sanitize_error_text(response.text or "", self.api_key)

        if status in (401, 403):
            raise ProviderAuthError(
                f"{self.display_name}: API key ditolak (HTTP {status})."
            )
        if status == 404:
            raise ProviderModelNotFoundError(
                f"{self.display_name}: model '{self.model}' tidak ditemukan (HTTP 404)."
            )
        if status == 429:
            raise ProviderUnavailableError(
                f"{self.display_name}: rate limit tercapai (HTTP 429)."
            )
        if status >= 500:
            raise ProviderUnavailableError(
                f"{self.display_name}: server sedang tidak tersedia (HTTP {status})."
            )

        logger.warning(
            "%s: HTTP %s tidak dikenal — body(sanitized)=%r",
            self.display_name,
            status,
            body_text,
        )
        raise ProviderResponseError(
            f"{self.display_name}: mengembalikan error (HTTP {status})."
        )

    # --------------------------------------------------------------
    # MODELS / HEALTH
    # --------------------------------------------------------------

    def get_models(self) -> List[str]:
        if not self.api_key:
            return []
        try:
            response = httpx.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            return [
                str(item.get("id") or "").strip()
                for item in items
                if isinstance(item, dict) and item.get("id")
            ]
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.warning("%s: gagal mengambil daftar model: %s", self.display_name, exc)
            return []

    def health_check(self) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth(
                configured=False,
                available=False,
                detail=f"{self.display_name}: belum dikonfigurasi.",
            )

        try:
            response = httpx.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=8,
            )
            if response.status_code in (401, 403):
                return ProviderHealth(
                    configured=True,
                    available=False,
                    detail=f"{self.display_name}: API key ditolak.",
                )
            response.raise_for_status()
            return ProviderHealth(
                configured=True,
                available=True,
                detail=f"{self.model} via {self.base_url}",
            )
        except Exception:
            return ProviderHealth(
                configured=True,
                available=False,
                detail=f"{self.display_name} sedang tidak dapat dihubungi.",
            )
